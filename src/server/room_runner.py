# SPDX-License-Identifier: MIT
"""The room's scheduler.

One pass asks three questions in a fixed order: what died, what can be handed
out, and where does that leave the room. Reclaim must come first — an expired
lease counted as a live turn would park the room in `working` forever.

Nothing here knows what a staging is. The caller injects `dispatch`, so the
scheduler can be tested against a fake and the real one can grow a jail later
without this file moving.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from src.memory.room_plan import RoomPlanStore
from src.memory.rooms import RoomStore
from src.server.room_phase import decide_phase, is_dispatchable

LEASE_SECONDS = 900
MAX_ATTEMPTS = 3
WORK_IN_FLIGHT_MAX = 2


def _parse(stamp: str | None) -> datetime | None:
    if not stamp:
        return None
    try:
        parsed = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class RoomRunner:
    def __init__(
        self,
        rooms: RoomStore,
        plans: RoomPlanStore,
        dispatch: Callable[[Any, Any, Any], Awaitable[None]],
        emit: Callable[[dict], Awaitable[None]],
        *,
        lease_seconds: int = LEASE_SECONDS,
        max_attempts: int = MAX_ATTEMPTS,
        max_in_flight: int = WORK_IN_FLIGHT_MAX,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.rooms = rooms
        self.plans = plans
        self.dispatch = dispatch
        self.emit = emit
        self.lease_seconds = lease_seconds
        self.max_attempts = max_attempts
        self.max_in_flight = max_in_flight
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._inflight: dict[int, set[str]] = {}

    def inflight(self, room_id: int) -> int:
        return len(self._inflight.get(room_id, ()))

    async def _push_board(self, room: Any) -> None:
        await self.emit({
            "type": "room.plan.updated",
            "room_id": room.id,
            "items": [i.to_dict() for i in self.plans.list(room.id)],
        })

    async def reclaim(self, room: Any) -> int:
        """Expire leases whose turn is gone.

        The attempt counter is what turns a member that keeps dying into a
        `blocked` item instead of an endless retry.
        """
        reclaimed = 0
        moment = self._now()
        running = self._inflight.get(room.id, set())
        for item in self.plans.list(room.id):
            if str(item.status) != "doing":
                continue
            if item.item_key in running:
                continue
            expires = _parse(item.lease_expires_at)
            if expires is not None and expires > moment:
                continue
            attempts = self.plans.bump_attempts(room.id, item.item_key)
            if attempts >= self.max_attempts:
                self.plans.set_status(
                    room.id, item.item_key, "blocked",
                    evidence=f"gave up after {attempts} attempts",
                )
            else:
                self.plans.clear_lease(room.id, item.item_key)
                self.plans.set_status(room.id, item.item_key, "todo", evidence="")
            reclaimed += 1
        if reclaimed:
            await self._push_board(room)
        return reclaimed

    async def tick(self, room: Any) -> str:
        if str(room.phase) not in {"planning", "working"}:
            return "idle"
        await self.reclaim(room)
        room = self.rooms.get(room.id)
        if room is None:
            return "idle"

        handed_out = 0
        if str(room.phase) == "working":
            free = self.max_in_flight - self.inflight(room.id)
            for item in self.plans.list(room.id):
                if free <= 0:
                    break
                if not is_dispatchable(item):
                    continue
                lease = (self._now() + timedelta(seconds=self.lease_seconds)).isoformat()
                self.plans.claim(room.id, item.item_key, lease)
                self._inflight.setdefault(room.id, set()).add(item.item_key)
                free -= 1
                handed_out += 1
                asyncio.ensure_future(self._run(room, item))
            if handed_out:
                await self._push_board(room)

        items = self.plans.list(room.id)
        busy = self.inflight(room.id) > 0 or any(
            str(i.status) == "doing" for i in items
        )
        decision = decide_phase(
            str(room.phase), items, in_flight=self.inflight(room.id),
        )
        if decision is None:
            if handed_out:
                return "dispatched"
            return "busy" if busy else "idle"
        next_phase, reason = decision
        self.rooms.update(room.id, phase=next_phase)
        await self.emit({
            "type": "room.phase.changed",
            "room_id": room.id,
            "phase": next_phase,
            "reason": reason,
        })
        return reason

    async def _run(self, room: Any, item: Any) -> None:
        """Hand one item over.

        Dispatch owns the staging and the turn; this method owns only the
        bookkeeping around it.
        """
        try:
            await self.dispatch(room, item, None)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        finally:
            self._inflight.get(room.id, set()).discard(item.item_key)

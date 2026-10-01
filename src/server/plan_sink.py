# SPDX-License-Identifier: MIT
"""Where plan_write puts its list.

The tool is meant to move into chat mode later, so the storage decision lives
behind one call. Today there is exactly one implementation; a second one is
what the protocol is for.
"""

from __future__ import annotations

from typing import Any, Protocol

from src.memory.room_plan import RoomPlanStore
from src.memory.rooms import RoomStore


class PlanSink(Protocol):
    def replace(self, items: list[dict]) -> list[dict]:
        """Write the whole list and return the board as it now stands."""
        ...


def _validated_owner(raw: Any, member_ids: set[int]) -> tuple[str | None, str | None]:
    """Only a member of this room may own an item.

    P3 dispatches to character cards only, so a well-formed agent owner is not
    an owner either — nothing would ever pick it up, and leaving it in place
    would make the item look assigned.
    """
    if not isinstance(raw, dict):
        return None, None
    kind = str(raw.get("kind") or "").strip()
    ref = str(raw.get("ref") or "").strip()
    if kind != "character" or not ref:
        return None, None
    try:
        ref_id = int(ref)
    except (TypeError, ValueError):
        return None, None
    if ref_id not in member_ids:
        return None, None
    return kind, ref


class RoomPlanSink:
    def __init__(self, rooms: RoomStore, plans: RoomPlanStore, room_id: int) -> None:
        self.rooms = rooms
        self.plans = plans
        self.room_id = room_id
        self.last_written: list[dict] = []

    def replace(self, items: list[dict]) -> list[dict]:
        member_ids = set(self.rooms.members(self.room_id))
        cleaned: list[dict] = []
        for raw in items or []:
            if not isinstance(raw, dict):
                continue
            owner_kind, owner_ref = _validated_owner(raw.get("owner"), member_ids)
            entry = dict(raw)
            if owner_kind is None:
                entry.pop("owner", None)
            else:
                entry["owner"] = {"kind": owner_kind, "ref": owner_ref}
            cleaned.append(entry)
        written = [item.to_dict() for item in self.plans.replace(self.room_id, cleaned)]
        self.last_written = written
        return written

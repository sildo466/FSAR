# SPDX-License-Identifier: MIT
"""The LAN routes.

Kept apart from room_app.py so the app's surface — what exists at all — can be
read in one place, and so every handler has to pass through the same
auth_guard. Index, state and messages land here; the doc lives in agent_doc.py.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request

from src.server.room_app import READ_BUDGET, RoomDeps, audit, auth_guard, require_room


def register_routes(app: Any, deps: RoomDeps) -> None:
    _index(app, deps)


def _read_budget(deps: RoomDeps, outcome: Any, request: Request) -> None:
    """One place for the per-credential read budget, shared by the readers."""
    limit, per_seconds, burst = READ_BUDGET
    if not deps.budget.allow(
        f"read:{outcome.token_id}", limit=limit, per_seconds=per_seconds,
        burst=burst,
    ):
        raise HTTPException(status_code=429, detail="rate_limited")


def _index(app: Any, deps: RoomDeps) -> None:
    @app.get("/room/index")
    async def room_index(request: Request) -> dict[str, Any]:
        outcome = auth_guard(deps, request)
        _read_budget(deps, outcome, request)

        room = require_room(deps, request, outcome.room_id, outcome)
        member = deps.members.get(room.id, outcome.member_ref)
        audit(deps, request, action="lan_read", result="allow", reason="ok",
              room_id=room.id, member_ref=outcome.member_ref,
              token_id=outcome.token_id)
        return {
            "rooms": [
                {
                    "room_id": room.id,
                    "name": room.name,
                    "member_ref": outcome.member_ref,
                    "display_name": getattr(member, "display_name", "")
                    or outcome.member_ref,
                    "state": getattr(member, "state", "active"),
                    "max_rounds": int(getattr(room, "max_rounds", 0) or 0),
                }
            ]
        }

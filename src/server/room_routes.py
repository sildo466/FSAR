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
    _state(app, deps)


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


def _speaker_name(
    deps: RoomDeps, room: Any, row: Any, agent_names: dict[str, str],
) -> str:
    """Name a row's speaker for a reader that is not the GUI.

    Deliberately a local copy rather than the group handler's: that one needs
    the GUI engine singleton, and this app has to be constructible without it.
    """
    if getattr(row, "speaker_kind", None) == "agent":
        return agent_names.get(getattr(row, "speaker_ref", None) or "", "Unknown")
    if row.role == "user":
        card = None
        if deps.cards is not None:
            user_card_id = getattr(room, "user_card_id", None)
            card = (
                deps.cards.get_user_card(user_card_id) if user_card_id else None
            ) or deps.cards.get_default_user_card()
        return getattr(card, "name", "") or "user"
    if deps.cards is None or not row.character_card_id:
        return "Unknown"
    character = deps.cards.get_character(row.character_card_id)
    return getattr(character, "name", "") or "Unknown"


def _state(app: Any, deps: RoomDeps) -> None:
    @app.get("/room/{room_id}/state")
    async def room_state(
        request: Request, room_id: int, since: int = 0,
    ) -> dict[str, Any]:
        outcome = auth_guard(deps, request)
        _read_budget(deps, outcome, request)

        room = require_room(deps, request, room_id, outcome)
        agent_names = {
            member.ref: member.display_name for member in deps.members.members(room.id)
        }
        rows = deps.rooms.session_store.get_session_messages(room.session_id)
        cursor = max(0, int(since))
        pending = [row for row in rows if int(row.id) > cursor]
        truncated = len(pending) > deps.history_limit
        page = pending[: deps.history_limit]

        audit(deps, request, action="lan_read", result="allow", reason="ok",
              room_id=room.id, member_ref=outcome.member_ref,
              token_id=outcome.token_id, detail=f"since={cursor}")
        return {
            "room_id": room.id,
            "room_name": room.name,
            "member_ref": outcome.member_ref,
            "next_since": int(page[-1].id) if page else cursor,
            "truncated": truncated,
            "messages": [
                {
                    "row_id": int(row.id),
                    "role": row.role,
                    "speaker_name": _speaker_name(deps, room, row, agent_names),
                    "speaker_kind": getattr(row, "speaker_kind", None),
                    "content": row.content,
                    "created_at": row.timestamp.isoformat(),
                }
                for row in page
            ],
        }

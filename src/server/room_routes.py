# SPDX-License-Identifier: MIT
"""The LAN routes.

Kept apart from room_app.py so the app's surface — what exists at all — can be
read in one place, and so every handler has to pass through the same
auth_guard. Index, state and messages live here; the doc is in agent_doc.py.

room_app is referenced as a module, not by importing its constants by value:
the budgets are patched in tests, and a by-value import would freeze them.
"""

from __future__ import annotations

import asyncio
import hashlib
from typing import Any

from fastapi import HTTPException, Request

from src.server import room_app
from src.server.room_app import RoomDeps

# A refusal from P1's shared entry point is a plain code; the LAN surface has
# to give it a status. Anything unmapped is a bad request rather than a 500 —
# the caller sent something the room would not take.
_P1_CODE_STATUS = {
    "empty": 400,
    "too_long": 413,
    "bad_json": 400,
    "muted": 403,
    "no_member": 404,
    "no_room": 404,
    "not_ready": 503,
}


def register_routes(app: Any, deps: RoomDeps) -> None:
    _index(app, deps)
    _state(app, deps)
    _messages(app, deps)
    _doc(app, deps)


def _row_id(raw: str | None, field: str) -> int:
    """A number from the path or the query, refused the way everything else is.

    Declaring these as typed parameters hands validation to FastAPI, which
    answers before authentication with a pydantic error body — a different
    shape from every other refusal on this surface, and one that names the
    framework underneath it.
    """
    try:
        value = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        value = -1
    if value < 0:
        raise HTTPException(status_code=400, detail=f"bad_{field}")
    return value


def _read_budget(deps: RoomDeps, outcome: Any) -> None:
    """One place for the per-credential read budget, shared by the readers."""
    limit, per_seconds, burst = room_app.READ_BUDGET
    if not deps.budget.allow(
        f"read:{outcome.token_id}", limit=limit, per_seconds=per_seconds,
        burst=burst,
    ):
        raise HTTPException(status_code=429, detail="rate_limited")


def _index(app: Any, deps: RoomDeps) -> None:
    @app.get("/room/index")
    async def room_index(request: Request) -> dict[str, Any]:
        outcome = room_app.auth_guard(deps, request)
        _read_budget(deps, outcome)

        room = room_app.require_room(deps, request, outcome.room_id, outcome)
        member = deps.members.get(room.id, outcome.member_ref)
        room_app.audit(deps, request, action="lan_read", result="allow",
                       reason="ok", room_id=room.id,
                       member_ref=outcome.member_ref, token_id=outcome.token_id)
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
        request: Request, room_id: str, since: str | None = None,
    ) -> dict[str, Any]:
        outcome = room_app.auth_guard(deps, request)
        rid = _row_id(room_id, "room_id")
        _read_budget(deps, outcome)

        room = room_app.require_room(deps, request, rid, outcome)
        agent_names = {
            member.ref: member.display_name
            for member in deps.members.members(room.id)
        }
        rows = deps.rooms.session_store.get_session_messages(room.session_id)
        # Required, not defaulted: an absent or negative cursor used to mean
        # "everything", which reads whole rooms out in one response and hides
        # the caller's own mistake behind a plausible answer.
        if since is None:
            raise HTTPException(status_code=400, detail="since_required")
        cursor = _row_id(since, "since")
        pending = [row for row in rows if int(row.id) > cursor]
        truncated = len(pending) > deps.history_limit
        page = pending[: deps.history_limit]

        room_app.audit(deps, request, action="lan_read", result="allow",
                       reason="ok", room_id=room.id,
                       member_ref=outcome.member_ref, token_id=outcome.token_id,
                       detail=f"since={cursor}")
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


def _messages(app: Any, deps: RoomDeps) -> None:
    @app.post("/room/{room_id}/messages")
    async def post_message(request: Request, room_id: str) -> dict[str, Any]:
        # Authorization precedes the idempotency cache on purpose: a revoked
        # credential must not be able to replay an answer it once earned.
        outcome = room_app.auth_guard(deps, request)
        rid = _row_id(room_id, "room_id")
        room = room_app.require_room(deps, request, rid, outcome)

        idempotency_key = request.headers.get("idempotency-key", "").strip()
        if not idempotency_key:
            raise HTTPException(
                status_code=400, detail="idempotency_key_required",
            )

        raw = await room_app.read_body(request)
        payload = room_app.read_json_object(request, raw)
        if set(payload) - {"content"}:
            raise HTTPException(status_code=400, detail="unknown_field")
        content = payload.get("content")
        if not isinstance(content, str):
            # str() would turn 123 into "123" and null into "None" and say it
            # out loud in the room, so a wrong type is the caller's error.
            raise HTTPException(status_code=400, detail="bad_content")
        if len(content.encode("utf-8")) > room_app.MAX_CONTENT_BYTES:
            raise HTTPException(status_code=413, detail="too_long")

        # The budgets bound the room's work, so they are spent only on a
        # request the room would take. Spent earlier, a client retrying a
        # malformed payload would burn its allowance on refusals and lose the
        # send that was fine.
        limit, per_seconds, burst = room_app.SPEAK_BUDGET
        if not deps.budget.allow(
            f"speak:{outcome.token_id}", limit=limit, per_seconds=per_seconds,
            burst=burst,
        ):
            raise HTTPException(status_code=429, detail="rate_limited")
        room_limit, room_window, room_burst = room_app.ROOM_SPEAK_BUDGET
        if not deps.budget.allow(
            f"room-speak:{room.id}", limit=room_limit,
            per_seconds=room_window, burst=room_burst,
        ):
            raise HTTPException(status_code=429, detail="rate_limited")

        scope = f"room:{room.id}:member:{outcome.member_ref}"
        digest = hashlib.sha256(raw).hexdigest()
        if deps.idempotency is not None:
            verdict, stored = deps.idempotency.lookup(
                scope, idempotency_key, digest,
            )
            if verdict == "replay" and stored is not None:
                return stored
            if verdict == "conflict":
                raise HTTPException(
                    status_code=409, detail="idempotency_conflict",
                )

        # Last, because it is the one expensive step: the budgets above bound
        # how often it can be reached, and a replay never runs it again.
        if deps.visitor_screen is not None:
            verdict = await asyncio.to_thread(
                deps.visitor_screen.screen, content,
            )
            if verdict.flagged:
                room_app.ban_visitor(deps, request, outcome, verdict, content)
                raise HTTPException(status_code=403, detail="banned")

        from src.server.handlers.group import post_member_message

        result = await post_member_message(
            room_id=room.id, member_ref=outcome.member_ref, content=content,
            ws=None,
        )
        if not result.get("ok"):
            code = str(result.get("code", "error"))
            room_app.audit(deps, request, action="lan_message", result="deny",
                           reason=code, room_id=room.id,
                           member_ref=outcome.member_ref,
                           token_id=outcome.token_id)
            raise HTTPException(
                status_code=_P1_CODE_STATUS.get(code, 400), detail=code,
            )

        body = {"row_id": result.get("row_id")}
        if deps.idempotency is not None:
            deps.idempotency.remember(scope, idempotency_key, digest, 200, body)
        room_app.audit(deps, request, action="lan_message", result="allow",
                       reason="ok", room_id=room.id,
                       member_ref=outcome.member_ref, token_id=outcome.token_id)
        return body


def _doc(app: Any, deps: RoomDeps) -> None:
    from fastapi.responses import PlainTextResponse

    from src.server.agent_doc import agent_md

    @app.get("/room/agent.md")
    async def agent_doc(request: Request) -> PlainTextResponse:
        outcome = room_app.auth_guard(deps, request)
        _read_budget(deps, outcome)
        # A credential whose membership is gone must not keep reading the
        # protocol, even though the token itself is still valid.
        room = room_app.require_room(deps, request, outcome.room_id, outcome)
        room_app.audit(deps, request, action="lan_doc", result="allow",
                       reason="ok", room_id=room.id,
                       member_ref=outcome.member_ref, token_id=outcome.token_id)
        return PlainTextResponse(
            agent_md(bool(getattr(room, "agent_mode", False))),
            media_type="text/markdown",
        )

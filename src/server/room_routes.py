# SPDX-License-Identifier: MIT
"""The LAN routes.

Kept apart from room_app.py so the app's surface — what exists at all — can be
read in one place, and so every handler has to pass through the same
auth_guard. Index, state, messages and the published snapshot live here; the
doc is in agent_doc.py.

room_app is referenced as a module, not by importing its constants by value:
the budgets are patched in tests, and a by-value import would freeze them.
"""

from __future__ import annotations

import asyncio
import hashlib
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse

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
    _publish(app, deps)
    _patches(app, deps)
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


def room_members(deps: RoomDeps, room: Any) -> list[dict[str, Any]]:
    """Everyone the room can hear from, by the ref a member addresses them with.

    A character and a token-holding member are different things — one speaks
    from inside the room, the other connects to it — so they are named as
    such. Names come from the card repo, so a room whose cards are not wired
    still lists its members."""
    out: list[dict[str, Any]] = []
    if deps.members is not None:
        for member in deps.members.members(room.id):
            out.append({
                "kind": "agent",
                "ref": member.ref,
                "display_name": member.display_name,
                "state": member.state,
            })
    if deps.cards is not None and deps.rooms is not None:
        for card_id in deps.rooms.members(room.id):
            character = deps.cards.get_character(card_id)
            if character is not None:
                out.append({
                    "kind": "character",
                    "ref": str(card_id),
                    "display_name": getattr(character, "name", "") or "",
                    "state": "active",
                })
    return out


def _index(app: Any, deps: RoomDeps) -> None:
    @app.get("/room/index")
    async def room_index(request: Request) -> dict[str, Any]:
        outcome = room_app.auth_guard(deps, request)
        _read_budget(deps, outcome)

        room = room_app.require_room(deps, request, outcome.room_id, outcome)
        member, listed = await asyncio.gather(
            asyncio.to_thread(deps.members.get, room.id, outcome.member_ref),
            asyncio.to_thread(room_members, deps, room),
        )
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
                    "members": listed,
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


def plan_projection(plans: Any, room_id: int) -> list[dict[str, Any]]:
    """The board as a member may see it.

    Four fields, deliberately. `owner_ref`, `evidence`, `commit_ref` and
    `lease_expires_at` are the room's internal account — the lease especially,
    since it would tell a member who is working right now.
    """
    if plans is None:
        return []
    return [
        {
            "item_key": item.item_key,
            "text": item.text,
            "status": item.status,
            "owner_kind": item.owner_kind,
        }
        for item in plans.list(room_id)
    ]


def patch_projection(patches: Any, room_id: int) -> list[dict[str, Any]]:
    """What the room is holding, patch by patch, and where each one stands.

    Unlike the board's projection this keeps `member_ref`: a patch is a
    hand-off, and a sender that has just handed work over needs to see what
    became of it. The patch text is not here — it is somebody else's work, and
    a list is not the place to read it.
    """
    if patches is None:
        return []
    return [
        {
            "patch_id": record.id,
            "member_ref": record.member_ref,
            "item_key": record.item_key,
            "state": record.state,
            "verdict_reason": record.verdict_reason,
            "created_at": record.created_at,
            "decided_at": record.decided_at,
        }
        for record in patches.list(room_id)
    ]


def _state(app: Any, deps: RoomDeps) -> None:
    @app.get("/room/{room_id}/state")
    async def room_state(
        request: Request, room_id: str, since: str | None = None,
    ) -> dict[str, Any]:
        outcome = room_app.auth_guard(deps, request)
        rid = _row_id(room_id, "room_id")
        _read_budget(deps, outcome)

        room = room_app.require_room(deps, request, rid, outcome)
        # Every store here is synchronous SQLite, and the GUI thread writes the
        # same file while a room is live. A read that waits on that writer waits
        # while holding this loop, which is what refused connections — so the
        # reads that scale with the room go to a thread.
        member_list, rows = await asyncio.gather(
            asyncio.to_thread(deps.members.members, room.id),
            asyncio.to_thread(
                deps.rooms.session_store.get_session_messages, room.session_id,
            ),
        )
        agent_names = {member.ref: member.display_name for member in member_list}
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
        payload = {
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
        # Only a room that has a board and can run it gets the key at all: an
        # always-empty array reads like a promise about something that is not
        # there.
        if getattr(room, "agent_mode", False):
            if deps.plans is not None:
                payload["plan"] = await asyncio.to_thread(
                    plan_projection, deps.plans, room.id,
                )
            if deps.patches is not None:
                payload["patches"] = await asyncio.to_thread(
                    patch_projection, deps.patches, room.id,
                )
        return payload


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


def _publish(app: Any, deps: RoomDeps) -> None:
    from src.server.publish_export import package_for

    @app.get("/room/{room_id}/publish")
    async def room_publish(request: Request, room_id: str) -> FileResponse:
        outcome = room_app.auth_guard(deps, request)
        rid = _row_id(room_id, "room_id")
        _read_budget(deps, outcome)

        room = room_app.require_room(deps, request, rid, outcome)
        record = (
            deps.publishes.latest(room.id) if deps.publishes is not None else None
        )
        path = package_for(room.id, record.digest) if record is not None else None
        if path is None or not path.exists():
            # The same 404 every other absence gets: a room that has published
            # nothing must not be tellable from one that is not yours.
            room_app.audit(deps, request, action="lan_publish", result="deny",
                           reason="nothing_published", room_id=room.id,
                           member_ref=outcome.member_ref, token_id=outcome.token_id)
            raise HTTPException(status_code=404, detail="not_found")

        room_app.audit(deps, request, action="lan_publish", result="allow",
                       reason="ok", room_id=room.id,
                       member_ref=outcome.member_ref, token_id=outcome.token_id)
        return FileResponse(
            path, media_type="application/gzip", filename=path.name,
        )


def _patches(app: Any, deps: RoomDeps) -> None:
    from src.server.patch_text import check_patch

    @app.post("/room/{room_id}/patches")
    async def post_patch(request: Request, room_id: str) -> dict[str, Any]:
        outcome = room_app.auth_guard(deps, request)
        rid = _row_id(room_id, "room_id")
        room = room_app.require_room(deps, request, rid, outcome)
        if deps.patches is None:
            raise HTTPException(status_code=503, detail="not_ready")

        idempotency_key = request.headers.get("idempotency-key", "").strip()
        if not idempotency_key:
            raise HTTPException(
                status_code=400, detail="idempotency_key_required",
            )

        cap = room_app.MAX_PATCH_BYTES
        raw = await room_app.read_body(request, limit=cap)
        payload = room_app.read_json_object(request, raw, limit=cap)
        if set(payload) - {"patch", "item_key"}:
            raise HTTPException(status_code=400, detail="unknown_field")
        patch_text = payload.get("patch")
        if not isinstance(patch_text, str):
            raise HTTPException(status_code=400, detail="bad_patch")
        item_key = payload.get("item_key")
        if item_key is not None and not isinstance(item_key, str):
            raise HTTPException(status_code=400, detail="bad_item_key")

        # Shape first, so a malformed patch never spends the sender's
        # allowance and never reaches the queue.
        accepted, why = check_patch(patch_text, max_bytes=cap)
        if not accepted:
            room_app.audit(deps, request, action="lan_patch", result="deny",
                           reason=f"bad_patch: {why}", room_id=room.id,
                           member_ref=outcome.member_ref,
                           token_id=outcome.token_id)
            # The reason, not just the code: a refused patch is one of several
            # shapes, and a sender that cannot tell which is left guessing.
            raise HTTPException(
                status_code=400, detail={"code": "bad_patch", "reason": why},
            )

        limit, per_seconds, burst = room_app.PATCH_BUDGET
        if not deps.budget.allow(
            f"patch:{outcome.token_id}", limit=limit, per_seconds=per_seconds,
            burst=burst,
        ):
            raise HTTPException(status_code=429, detail="rate_limited")

        scope = f"room:{room.id}:patch:{outcome.member_ref}"
        digest = hashlib.sha256(raw).hexdigest()
        if deps.idempotency is not None:
            verdict, stored = deps.idempotency.lookup(scope, idempotency_key, digest)
            if verdict == "replay" and stored is not None:
                return stored
            if verdict == "conflict":
                raise HTTPException(status_code=409, detail="idempotency_conflict")

        record = await asyncio.to_thread(
            deps.patches.add, room.id, outcome.member_ref,
            patch_text=patch_text, digest=digest, size=len(raw),
            item_key=item_key,
        )
        body = {"patch_id": record.id, "state": record.state}
        if deps.idempotency is not None:
            deps.idempotency.remember(scope, idempotency_key, digest, 200, body)
        room_app.audit(deps, request, action="lan_patch", result="allow",
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

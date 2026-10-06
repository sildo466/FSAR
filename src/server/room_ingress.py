# SPDX-License-Identifier: MIT
"""Loopback ingress for room members that are not the local user.

Lives on the main app because phase 1 has no LAN listener at all — the
separate low-privilege app in the design doc exists to isolate a
network-facing surface, and there is none yet. Identity comes from the
member token only: the request body cannot name a room or a member.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from src.security.ws_auth import bearer_token

router = APIRouter()

_MEMBER_MAX_PER_MINUTE = 20
_MAX_CONTENT = 16 * 1024
_recent: dict[str, deque[float]] = defaultdict(deque)
_tokens: Any = None
_rooms: Any = None


def configure(member_tokens: Any, rooms: Any) -> None:
    global _tokens, _rooms
    _tokens = member_tokens
    _rooms = rooms


def _identity(request: Request) -> tuple[int, str]:
    token = bearer_token(request.headers.get("authorization"))
    resolved = _tokens.resolve(token) if (token and _tokens is not None) else None
    if resolved is None:
        raise HTTPException(status_code=401, detail="unauthorized")
    room_id, member_ref = resolved
    if _is_rate_limited(member_ref):
        raise HTTPException(status_code=429, detail="rate_limited")
    return room_id, member_ref


def _is_rate_limited(member_ref: str, *, now: float | None = None) -> bool:
    current = time.monotonic() if now is None else now
    hits = _recent[member_ref]
    while hits and current - hits[0] > 60:
        hits.popleft()
    return len(hits) >= _MEMBER_MAX_PER_MINUTE


def _record_hit(member_ref: str) -> None:
    _recent[member_ref].append(time.monotonic())


@router.post("/api/room/member/message")
async def post_member_message(request: Request) -> dict[str, Any]:
    from src.server.handlers.group import post_member_message as post

    room_id, member_ref = _identity(request)
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="bad_json")
    content = str((payload or {}).get("content", ""))
    if len(content) > _MAX_CONTENT:
        raise HTTPException(status_code=413, detail="too_long")
    result = await post(
        room_id=room_id, member_ref=member_ref, content=content, ws=None,
    )
    if result["ok"]:
        _record_hit(member_ref)
    return result


@router.get("/api/room/member/state")
async def get_member_state(request: Request, since: int = 0) -> dict[str, Any]:
    from src.server.handlers.group import _engine

    room_id, member_ref = _identity(request)
    room = _rooms.get(room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="not_found")
    rows = _engine.chat.session_store.get_session_messages(room.session_id)
    return {
        "room_id": room_id,
        "room_name": room.name,
        "member_ref": member_ref,
        "messages": [
            {
                "row_id": r.id,
                "role": r.role,
                "content": r.content,
                "speaker_kind": r.speaker_kind,
                "speaker_ref": r.speaker_ref,
                "character_id": r.character_card_id,
            }
            for r in rows
            if r.id > since
        ],
    }

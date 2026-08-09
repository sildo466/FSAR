# SPDX-License-Identifier: MIT
"""Conversation WS handler — routes conversation.* messages."""

from __future__ import annotations

from typing import Any

from fastapi import WebSocket

from src.server.chat_engine import ChatEngine
from src.utils.logger import logger

_engine: ChatEngine | None = None


def set_engine(engine: ChatEngine) -> None:
    global _engine
    _engine = engine


def prune_empty_sessions(store, active_id: str | None) -> None:
    """Drop untitled sessions with zero messages (e.g. slash-only chats)."""
    for row in store.list(limit=500):
        if (
            row.message_count == 0
            and not row.title.strip()
            and not row.pinned
            and row.id != active_id
        ):
            store.delete(row.id)


async def dispatch(ws: WebSocket, msg: dict[str, Any]) -> bool:
    t = msg.get("type")
    if _engine is None or not t.startswith("conversation."):
        return False

    store = _engine.session_store

    try:
        if t == "conversation.list":
            prune_empty_sessions(store, _engine.active_conversation_id())
            sessions = store.list(limit=int(msg.get("limit", 50)))
            await ws.send_json({
                "type": "conversation.list",
                "sessions": [s.to_dict() for s in sessions],
            })
            return True

        if t == "conversation.create":
            row = store.create()
            _engine.workspace_repo.get_or_create_binding(row.id)
            _engine._active_conv_id = row.id  # noqa: SLF001 — engine ownership
            await ws.send_json({
                "type": "conversation.created",
                "session": row.to_dict(),
            })
            return True

        if t == "conversation.switch":
            cid = str(msg.get("conversation_id", ""))
            ok = await _engine.switch_conversation(cid)
            if not ok:
                await ws.send_json({
                    "type": "error",
                    "code": "no_session",
                    "message": f"Unknown conversation_id: {cid}",
                })
                return True
            row = store.get(cid)
            await ws.send_json({
                "type": "conversation.switched",
                "conversation_id": cid,
                "session": row.to_dict() if row else None,
            })
            return True

        if t == "conversation.history":
            cid = str(msg.get("conversation_id", ""))
            limit = int(msg.get("limit", 100))
            msgs = store.get_session_messages(cid, limit=limit)
            # Enrich with the session's current character so old messages
            # that pre-date character_id tracking still render the right name.
            char_id = store.get_character(cid)
            char_name = None
            if char_id:
                c = _engine.card_repo.get_character(char_id)
                if c:
                    char_name = c.name
            enriched = []
            for m in msgs:
                d = m.to_dict()
                if d.get("role") == "assistant" and char_name:
                    d.setdefault("character_id", char_id)
                    d.setdefault("character_name", char_name)
                enriched.append(d)
            await ws.send_json({
                "type": "conversation.history",
                "conversation_id": cid,
                "messages": enriched,
            })
            return True

        if t == "conversation.rename":
            cid = str(msg.get("conversation_id", ""))
            title = str(msg.get("title", "")).strip()
            if not title:
                return True
            ok = store.rename(cid, title)
            if ok:
                await ws.send_json({
                    "type": "conversation.title_updated",
                    "conversation_id": cid,
                    "title": title,
                })
            return True

        if t == "conversation.pin":
            cid = str(msg.get("conversation_id", ""))
            pinned = bool(msg.get("pinned", False))
            store.set_pinned(cid, pinned)
            row = store.get(cid)
            if row:
                await ws.send_json({
                    "type": "conversation.updated",
                    "session": row.to_dict(),
                })
            return True

        if t == "conversation.delete":
            cid = str(msg.get("conversation_id", ""))
            store.delete(cid)
            _engine.sandbox_allow_cache.clear(cid)
            if _engine.active_conversation_id() == cid:
                _engine._active_conv_id = None  # noqa: SLF001
            await ws.send_json({
                "type": "conversation.deleted",
                "conversation_id": cid,
            })
            return True
    except Exception as e:
        logger.warning(f"{t} failed: {e}")
        await ws.send_json({
            "type": "error",
            "code": "conversation_handler",
            "message": str(e),
        })
        return True

    return False

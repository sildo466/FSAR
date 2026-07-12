# SPDX-License-Identifier: Apache-2.0
"""Chat WS handler — routes chat.* messages to the ChatEngine."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket

from src.server.chat_engine import ChatEngine
from src.utils.logger import logger

_engine: ChatEngine | None = None
_sockets: set[WebSocket] = set()


def set_engine(engine: ChatEngine) -> None:
    global _engine
    _engine = engine


def register_socket(ws: WebSocket) -> None:
    _sockets.add(ws)


def unregister_socket(ws: WebSocket) -> None:
    _sockets.discard(ws)


async def _broadcast(event: dict[str, Any]) -> None:
    dead: list[WebSocket] = []
    for s in list(_sockets):
        try:
            await s.send_json(event)
        except Exception:
            dead.append(s)
    for d in dead:
        _sockets.discard(d)


async def dispatch(ws: WebSocket, msg: dict[str, Any]) -> bool:
    """Returns True if msg was handled."""
    t = msg.get("type")
    if _engine is None:
        return False
    if t == "chat.send":
        asyncio.create_task(_engine.handle_send(
            ws,
            msg.get("content", ""),
            msg.get("mode", "agent"),
            msg.get("conversation_id"),
            msg.get("character_id"),
        ))
        return True
    if t == "chat.cancel":
        _engine.cancel()
        return True
    if t == "chat.rate":
        try:
            result = _engine.rate(
                str(msg.get("message_id", "")),
                int(msg.get("score", 0)),
                str(msg.get("reason", "") or ""),
            )
            await ws.send_json({
                "type": "chat.rate.ack",
                "message_id": str(msg.get("message_id", "")),
                **result,
            })
        except Exception as e:
            logger.warning(f"chat.rate failed: {e}")
            await ws.send_json({
                "type": "chat.rate.ack",
                "message_id": str(msg.get("message_id", "")),
                "status": "error",
                "error": str(e),
            })
        return True
    return False

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
_tasks: dict[WebSocket, asyncio.Task[None]] = {}


def set_engine(engine: ChatEngine) -> None:
    global _engine
    _engine = engine


def register_socket(ws: WebSocket) -> None:
    _sockets.add(ws)


def unregister_socket(ws: WebSocket) -> None:
    _sockets.discard(ws)
    task = _tasks.pop(ws, None)
    if task is not None:
        task.cancel()


def _start_chat(ws: WebSocket, msg: dict[str, Any]) -> None:
    previous = _tasks.get(ws)
    if previous is not None and not previous.done():
        previous.cancel()
    task = asyncio.create_task(_engine.handle_send(
        ws,
        msg.get("content", ""),
        msg.get("mode", "agent"),
        msg.get("conversation_id"),
        msg.get("character_id"),
    ))
    _tasks[ws] = task
    task.add_done_callback(lambda done: _tasks.pop(ws, None) if _tasks.get(ws) is done else None)


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
        _start_chat(ws, msg)
        return True
    if t == "chat.cancel":
        _engine.cancel()
        task = _tasks.get(ws)
        if task is not None and not task.done():
            task.cancel()
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

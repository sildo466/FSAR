# SPDX-License-Identifier: Apache-2.0
"""Chat WS handler — routes chat.* messages to the ChatEngine."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket

from src.server.chat_engine import ChatEngine
from src.utils.logger import logger

_engine: ChatEngine | None = None


def set_engine(engine: ChatEngine) -> None:
    global _engine
    _engine = engine


async def dispatch(ws: WebSocket, msg: dict[str, Any]) -> bool:
    """Returns True if msg was handled."""
    t = msg.get("type")
    if _engine is None:
        return False
    if t == "chat.send":
        # Run in the background so the WS receive loop stays free for
        # risk.respond / chat.cancel while the agent loop is working.
        asyncio.create_task(_engine.handle_send(
            ws, msg.get("content", ""), msg.get("mode", "agent"),
        ))
        return True
    if t == "chat.cancel":
        _engine.cancel()
        return True
    if t == "chat.rate":
        try:
            _engine.rate(
                str(msg.get("message_id", "")),
                int(msg.get("score", 0)),
                str(msg.get("reason", "") or ""),
            )
        except Exception as e:
            logger.warning(f"chat.rate failed: {e}")
        return True
    return False

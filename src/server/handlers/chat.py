# SPDX-License-Identifier: Apache-2.0
"""Chat WS handler — currently a mock that echoes; real Orchestrator wired in P7.3."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from fastapi import WebSocket


async def handle_chat_send(ws: WebSocket, content: str) -> None:
    """Mock echo: send thinking → delta stream → done."""
    message_id = f"msg_{uuid.uuid4().hex[:8]}"
    await ws.send_json({"type": "chat.thinking", "message_id": message_id})
    await asyncio.sleep(0.3)
    for word in f"Echo: {content}".split():
        await ws.send_json({"type": "chat.delta", "message_id": message_id, "content": word + " "})
        await asyncio.sleep(0.05)
    await ws.send_json({
        "type": "chat.done",
        "message_id": message_id,
        "outcome": "success",
        "summary": "done",
    })


async def dispatch(ws: WebSocket, msg: dict[str, Any]) -> bool:
    """Returns True if msg was handled."""
    t = msg.get("type")
    if t == "chat.send":
        await handle_chat_send(ws, msg.get("content", ""))
        return True
    return False

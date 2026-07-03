# SPDX-License-Identifier: Apache-2.0
"""Chat WS handler — currently a mock that echoes; real Orchestrator wired in P7.3."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from fastapi import WebSocket

from src.server.risk_bridge import RiskBridge

_bridge: RiskBridge | None = None


def set_bridge(bridge: RiskBridge) -> None:
    global _bridge
    _bridge = bridge


async def handle_chat_send(ws: WebSocket, content: str) -> None:
    """Mock echo with a synthetic MEDIUM tool call to exercise the confirm flow."""
    message_id = f"msg_{uuid.uuid4().hex[:8]}"
    await ws.send_json({"type": "chat.thinking", "message_id": message_id})
    await asyncio.sleep(0.2)

    call_id = f"call_{uuid.uuid4().hex[:8]}"
    args = {"action": "send wechat", "to": "sunny", "text": content}
    await ws.send_json({
        "type": "chat.tool_call",
        "message_id": message_id,
        "call_id": call_id,
        "tool": "mock_wechat_send",
        "args": args,
        "risk": "MEDIUM",
    })

    if _bridge is not None:
        args_preview = json.dumps(args, ensure_ascii=False)
        result = await _bridge.submit(
            call_id, "mock_wechat_send", args_preview, "synthetic test",
            timeout=10.0,
        )
        await ws.send_json({
            "type": "chat.tool_result",
            "call_id": call_id,
            "result": f"decision={result.value}",
            "latency_ms": 0,
        })
    else:
        await ws.send_json({
            "type": "chat.tool_result",
            "call_id": call_id,
            "result": "skipped (no bridge)",
            "latency_ms": 0,
        })

    await ws.send_json({"type": "chat.delta", "message_id": message_id, "content": f"Echo: {content}"})
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

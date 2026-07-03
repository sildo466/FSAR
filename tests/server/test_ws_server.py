# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from fastapi.testclient import TestClient

from src.server.ws_server import app


def test_ws_receives_snapshot_on_connect():
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "snapshot"
        assert "config" in msg


def test_ws_chat_send_echoes_back():
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()  # snapshot
        ws.send_json({"type": "chat.send", "content": "hello"})
        msgs = []
        for _ in range(40):
            m = ws.receive_json()
            msgs.append(m)
            if m.get("type") == "chat.tool_call":
                ws.send_json({
                    "type": "risk.respond",
                    "call_id": m["call_id"],
                    "response": "y",
                })
            if m.get("type") == "chat.done":
                break
        types = [m["type"] for m in msgs]
        assert "chat.thinking" in types
        assert "chat.delta" in types
        assert "chat.done" in types
        assert "chat.tool_call" in types
        assert "chat.tool_result" in types


def test_ws_risk_respond_unblocks_tool():
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "chat.send", "content": "ping"})
        call_id = None
        for _ in range(40):
            m = ws.receive_json()
            if m.get("type") == "chat.tool_call":
                call_id = m["call_id"]
                break
        assert call_id is not None
        ws.send_json({"type": "risk.respond", "call_id": call_id, "response": "n"})
        for _ in range(40):
            m = ws.receive_json()
            if m.get("type") == "chat.tool_result":
                assert "decision=n" in m["result"]
                break
            if m.get("type") == "chat.done":
                break

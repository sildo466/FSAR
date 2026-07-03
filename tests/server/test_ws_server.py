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
        for _ in range(20):
            m = ws.receive_json()
            msgs.append(m)
            if m.get("type") == "chat.done":
                break
        types = [m["type"] for m in msgs]
        assert "chat.thinking" in types
        assert "chat.delta" in types
        assert "chat.done" in types

# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

import src.server.chat_engine as ce
import src.server.ws_server as ws_mod
from src.server.ws_server import app


def test_ws_receives_snapshot_on_connect():
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "snapshot"
        assert "config" in msg


def test_ws_risk_decline_cancels_tool(monkeypatch):
    engine = ws_mod._engine
    monkeypatch.setattr(engine, "client_and_model", lambda: (object(), "model-x", "prov"))

    calls = iter([
        SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(
                content=None,
                tool_calls=[SimpleNamespace(
                    id="c1",
                    function=SimpleNamespace(
                        name="file_ops",
                        arguments=json.dumps({"action": "delete", "path": "x"}),
                    ),
                )],
            ))],
            usage=None,
        ),
        SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(
                content="ok, cancelled", tool_calls=None,
            ))],
            usage=None,
        ),
    ])
    monkeypatch.setattr(ce, "chat_completion", lambda *a, **k: next(calls))
    verdict = SimpleNamespace(
        needs_confirm=lambda: True,
        is_denied=lambda: False,
        effective_risk="HIGH",
        reason="test",
    )
    monkeypatch.setattr(engine.risk_engine, "evaluate", lambda tool, args: verdict)

    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "chat.send", "content": "delete it", "mode": "agent"})
        result = None
        for _ in range(40):
            m = ws.receive_json()
            if m.get("type") == "chat.tool_call":
                ws.send_json({"type": "risk.respond", "call_id": m["call_id"], "response": "n"})
            if m.get("type") == "chat.tool_result":
                result = m["result"]
            if m.get("type") == "chat.done":
                break
        assert result is not None
        assert "CANCELLED" in result

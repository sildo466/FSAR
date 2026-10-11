# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from src.core.agent_tiers import get_tier_profile
import src.server.chat_engine as ce
import src.server.ws_server as ws_mod


def _resp(content: str | None = None, tool_calls: list | None = None):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(
            content=content, tool_calls=tool_calls,
        ))],
        usage={"prompt_tokens": 10, "completion_tokens": 3, "cached_tokens": 0},
    )


def _tool_call(call_id: str, name: str, args: dict):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=json.dumps(args)),
    )


def _collect_until_done(ws, limit: int = 50) -> list[dict]:
    msgs = []
    for _ in range(limit):
        m = ws.receive_json()
        msgs.append(m)
        if m.get("type") in ("chat.done",):
            break
    return msgs


def test_chat_send_no_provider_emits_error(monkeypatch):
    monkeypatch.setattr(ws_mod._engine, "client_and_model", lambda: (None, "", ""))
    client = TestClient(ws_mod.app)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "chat.send", "content": "hello", "mode": "agent"})
        msgs = _collect_until_done(ws)
    types = [m["type"] for m in msgs]
    assert "error" in types
    assert any(m.get("code") == "no_provider" for m in msgs if m["type"] == "error")
    assert msgs[-1]["outcome"] == "failure"


def test_chat_send_agent_returns_llm_text(monkeypatch):
    # low tier: no self-check/debate, so the agent streams a single turn
    monkeypatch.setattr(ce, "get_tier_profile", lambda name: get_tier_profile("low"))
    monkeypatch.setattr(ws_mod._engine, "client_and_model", lambda: (object(), "model-x", "prov"))
    monkeypatch.setattr(ce, "chat_completion", lambda *a, **k: _resp(content="hi there"))
    monkeypatch.setattr(ws_mod._engine, "_save_user", lambda *a, **k: None)
    monkeypatch.setattr(ws_mod._engine, "_save_assistant", lambda *a, **k: None)
    monkeypatch.setattr(ws_mod._engine, "_reflect", lambda *a, **k: None)
    client = TestClient(ws_mod.app)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "chat.send", "content": "hello", "mode": "agent"})
        msgs = _collect_until_done(ws)
    types = [m["type"] for m in msgs]
    assert "chat.thinking" in types
    assert "".join(m["content"] for m in msgs if m["type"] == "chat.delta") == "hi there"
    assert msgs[-1]["outcome"] == "success"


def test_chat_send_tool_call_routes_through_risk_bridge(monkeypatch):
    engine = ws_mod._engine
    # low tier: no self-check, so one tool turn + one final answer turn
    monkeypatch.setattr(ce, "get_tier_profile", lambda name: get_tier_profile("low"))
    monkeypatch.setattr(engine, "client_and_model", lambda: (object(), "model-x", "prov"))
    monkeypatch.setattr(engine, "_save_user", lambda *a, **k: None)
    monkeypatch.setattr(engine, "_save_assistant", lambda *a, **k: None)
    monkeypatch.setattr(engine, "_reflect", lambda *a, **k: None)

    calls = iter([
        _resp(tool_calls=[_tool_call("c1", "file_ops", {"action": "list", "path": "."})]),
        _resp(content="all done"),
    ])
    monkeypatch.setattr(ce, "chat_completion", lambda *a, **k: next(calls))

    verdict = SimpleNamespace(
        needs_confirm=lambda: True,
        is_denied=lambda: False,
        effective_risk="MEDIUM",
        reason="test confirm",
    )
    monkeypatch.setattr(engine.risk_engine, "evaluate", lambda tool, args, **kwargs: verdict)

    async def fake_execute(name, **kwargs):
        return "TOOL_OK"
    monkeypatch.setattr(engine.registry, "execute", fake_execute)

    client = TestClient(ws_mod.app)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "chat.send", "content": "do it", "mode": "agent"})
        msgs = []
        for _ in range(50):
            m = ws.receive_json()
            msgs.append(m)
            if m["type"] == "chat.tool_call":
                assert m["risk"] == "MEDIUM"
                ws.send_json({"type": "risk.respond", "call_id": m["call_id"], "response": "y"})
            if m["type"] == "chat.done":
                break
    types = [m["type"] for m in msgs]
    assert "chat.tool_call" in types
    result = next(m for m in msgs if m["type"] == "chat.tool_result")
    assert result["result"] == "TOOL_OK"
    assert "".join(m["content"] for m in msgs if m["type"] == "chat.delta") == "all done"


def test_chat_send_agent_streams_reasoning_chunks(monkeypatch):
    monkeypatch.setattr(ce, "get_tier_profile", lambda name: get_tier_profile("low"))
    monkeypatch.setattr(ws_mod._engine, "client_and_model", lambda: (object(), "model-x", "prov"))

    def _stream(*a, **k):
        return iter([
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="Hel", tool_calls=None))]),
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="lo!", tool_calls=None))]),
        ])

    monkeypatch.setattr(ce, "chat_completion", _stream)
    monkeypatch.setattr(ws_mod._engine, "_save_user", lambda *a, **k: None)
    monkeypatch.setattr(ws_mod._engine, "_save_assistant", lambda *a, **k: None)
    monkeypatch.setattr(ws_mod._engine, "_reflect", lambda *a, **k: None)

    client = TestClient(ws_mod.app)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "chat.send", "content": "hello", "mode": "agent"})
        msgs = _collect_until_done(ws)
    deltas = [m["content"] for m in msgs if m["type"] == "chat.delta"]
    assert "".join(deltas) == "Hello!"
    assert msgs[-1]["outcome"] == "success"


def test_chat_send_binds_selected_workspace_on_new_conversation(monkeypatch, tmp_path):
    import uuid

    engine = ws_mod._engine
    monkeypatch.setattr(ce, "get_tier_profile", lambda name: get_tier_profile("low"))
    monkeypatch.setattr(engine, "client_and_model", lambda: (object(), "model-x", "prov"))
    monkeypatch.setattr(ce, "chat_completion", lambda *a, **k: _resp(content="done"))
    monkeypatch.setattr(engine, "_save_user", lambda *a, **k: None)
    monkeypatch.setattr(engine, "_save_assistant", lambda *a, **k: None)
    monkeypatch.setattr(engine, "_reflect", lambda *a, **k: None)

    ws = engine.workspace_repo.create(
        name=f"sandbox-{uuid.uuid4().hex[:8]}", root_path=str(tmp_path / "a"),
    )
    try:
        client = TestClient(ws_mod.app)
        conv_id = None
        with client.websocket_connect("/ws") as wsock:
            wsock.receive_json()
            wsock.send_json({
                "type": "chat.send", "content": "hello", "mode": "agent",
                "workspace_id": ws.id,
            })
            for _ in range(40):
                m = wsock.receive_json()
                if m.get("type") == "conversation.created":
                    conv_id = m["session"]["id"]
                if m.get("type") == "chat.done":
                    break
        assert conv_id is not None
        assert engine.workspace_repo.get_binding(conv_id) == (conv_id, ws.id)
    finally:
        engine.workspace_repo.delete(ws.id)


def test_slash_command_executes_server_side(monkeypatch):
    client = TestClient(ws_mod.app)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "chat.send", "content": "/tools", "mode": "agent"})
        msgs = _collect_until_done(ws)
    text = "".join(m["content"] for m in msgs if m["type"] == "chat.delta")
    assert "Tools" in text
    assert msgs[-1]["outcome"] == "success"


class _RecordingWS:
    def __init__(self):
        self.events: list[dict] = []

    async def send_json(self, event: dict) -> None:
        self.events.append(event)


def _streamed_turn(monkeypatch, chunks) -> dict:
    import asyncio

    monkeypatch.setattr(ce, "chat_completion", lambda *a, **k: iter(chunks))
    return asyncio.run(ws_mod._engine._stream_agent_completion(
        client=object(),
        provider_id="prov",
        call_kwargs={"model": "model-x", "messages": []},
        stream_sink=(_RecordingWS(), "message", "conversation"),
    ))


def test_streamed_turn_without_tool_calls_carries_no_tool_calls_key(monkeypatch):
    # The loop re-sends this message (the self-check turn appends it and asks
    # again), and an explicit null is a 400 for strict OpenAI-compatible
    # gateways: "Invalid input: expected array, received null".
    message = _streamed_turn(monkeypatch, [
        SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(
            content="hi", tool_calls=None,
        ))]),
    ])
    assert message["content"] == "hi"
    assert "tool_calls" not in message


def test_streamed_turn_with_tool_calls_keeps_them(monkeypatch):
    message = _streamed_turn(monkeypatch, [
        SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(
            content=None,
            tool_calls=[SimpleNamespace(
                index=0, id="c1",
                function=SimpleNamespace(name="file_ops", arguments='{"a": 1}'),
            )],
        ))]),
    ])
    assert message["tool_calls"] == [{
        "id": "c1", "type": "function",
        "function": {"name": "file_ops", "arguments": '{"a": 1}'},
    }]


def test_streamed_turn_failure_does_not_leak_the_provider_error(monkeypatch):
    # The rebuilt message's content is persisted and can be posted as a room
    # line, so the provider's own error body (which carries a trace_id) must
    # never travel in it — only a human sentence.
    import asyncio

    def _boom(*a, **k):
        raise RuntimeError(
            "Error code: 400 - {'error': {'message': "
            "'{\"message\":\"invalid request error trace_id: c95100714ccf88dd\"}'}}"
        )

    monkeypatch.setattr(ce, "chat_completion", _boom)
    message = asyncio.run(ws_mod._engine._stream_agent_completion(
        client=object(),
        provider_id="prov",
        call_kwargs={"model": "model-x", "messages": []},
        stream_sink=(_RecordingWS(), "message", "conversation"),
    ))

    assert "trace_id" not in message["content"]
    assert "Error code" not in message["content"]
    assert message["content"].strip()

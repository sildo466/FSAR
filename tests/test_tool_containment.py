# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import pytest

from src.server.chat_engine import ChatEngine, _tool_error_text


class _WS:
    def __init__(self) -> None:
        self.events: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.events.append(payload)


def test_error_text_maps_missing_file():
    text = _tool_error_text("edit", FileNotFoundError("nope.txt"))
    assert text.startswith("Error: edit could not find the path")
    assert "List the directory" in text


def test_error_text_maps_permission_denied():
    text = _tool_error_text("file_ops", PermissionError("denied"))
    assert text.startswith("Error: file_ops was denied by the OS")
    assert "Choose a path you can write" in text


def test_error_text_falls_back_to_generic():
    text = _tool_error_text("run_command", RuntimeError("boom"))
    assert text.startswith("Error: run_command failed (RuntimeError): boom")
    assert "Fix the arguments" in text


async def test_execute_guarded_contains_inner_exception(monkeypatch):
    engine = ChatEngine.__new__(ChatEngine)
    engine.config = {}

    async def _raise(*args, **kwargs):
        raise FileNotFoundError("missing.txt")

    monkeypatch.setattr(engine, "_execute_guarded_inner", _raise)
    ws = _WS()

    result = await engine._execute_guarded(
        ws, "msg-1", "call-1", "edit", {"file_path": "missing.txt"}, "conv-1",
    )

    assert result.startswith("Error: edit could not find the path")
    assert [e["type"] for e in ws.events] == ["chat.tool_call", "chat.tool_result"]
    assert ws.events[0]["call_id"] == "call-1"
    assert ws.events[0]["tool"] == "edit"
    assert ws.events[0]["args"] == {"file_path": "missing.txt"}
    results = [e for e in ws.events if e["type"] == "chat.tool_result"]
    assert len(results) == 1
    assert results[0]["call_id"] == "call-1"
    assert results[0]["result"] == result


async def test_execute_guarded_does_not_duplicate_existing_tool_call(monkeypatch):
    engine = ChatEngine.__new__(ChatEngine)
    engine.config = {}

    async def _call_then_raise(socket, *args, **kwargs):
        await socket.send_json({
            "type": "chat.tool_call",
            "message_id": "msg-1",
            "conversation_id": "conv-1",
            "call_id": "call-1",
            "tool": "edit",
            "args": {"file_path": "missing.txt"},
            "risk": "SAFE",
        })
        raise FileNotFoundError("missing.txt")

    monkeypatch.setattr(engine, "_execute_guarded_inner", _call_then_raise)
    ws = _WS()

    result = await engine._execute_guarded(
        ws, "msg-1", "call-1", "edit", {"file_path": "missing.txt"}, "conv-1",
    )

    assert result.startswith("Error: edit could not find the path")
    assert [e["type"] for e in ws.events] == ["chat.tool_call", "chat.tool_result"]
    assert len([e for e in ws.events if e["type"] == "chat.tool_call"]) == 1


import asyncio
from types import SimpleNamespace


def _runtime(parallel_tools: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        profile=SimpleNamespace(parallel_tools=parallel_tools),
        tool_steps=[],
        serial_tool_lock=asyncio.Lock(),
    )


def _call(call_id: str, name: str) -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": "{}"},
    }


async def test_execute_tool_calls_contains_a_raising_tool(monkeypatch):
    engine = ChatEngine.__new__(ChatEngine)
    engine.config = {}
    monkeypatch.setattr(engine, "_can_parallel_tool", lambda name, args: False)

    async def _execute(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(engine, "_execute_runtime_tool", _execute)
    ws = _WS()

    results = await engine._execute_tool_calls(
        ws=ws,
        message_id="msg-1",
        conv_id="conv-1",
        client=None,
        model="",
        provider_id="",
        runtime=_runtime(),
        agent_id="agent-1",
        depth=0,
        tool_calls=[_call("call-1", "run_command")],
    )

    assert results[0][0] == "call-1"
    assert results[0][2].startswith("Error: run_command failed (RuntimeError): boom")
    assert results[0][3] is True
    assert [e["type"] for e in ws.events] == ["chat.tool_call", "chat.tool_result"]
    assert ws.events[0]["call_id"] == "call-1"
    assert ws.events[1]["call_id"] == "call-1"
    assert ws.events[1]["result"] == results[0][2]


async def test_parallel_batch_survives_one_raising_tool(monkeypatch):
    engine = ChatEngine.__new__(ChatEngine)
    engine.config = {}
    monkeypatch.setattr(engine, "_can_parallel_tool", lambda name, args: True)

    async def _execute(**kwargs):
        if kwargs["name"] == "bad":
            raise RuntimeError("boom")
        return "ok"

    monkeypatch.setattr(engine, "_execute_runtime_tool", _execute)
    ws = _WS()

    results = await engine._execute_tool_calls(
        ws=ws,
        message_id="msg-1",
        conv_id="conv-1",
        client=None,
        model="",
        provider_id="",
        runtime=_runtime(parallel_tools=True),
        agent_id="agent-1",
        depth=0,
        tool_calls=[_call("call-1", "bad"), _call("call-2", "good")],
    )

    by_id = {item[0]: item for item in results}
    assert by_id["call-1"][3] is True
    assert by_id["call-1"][2].startswith("Error: bad failed")
    assert by_id["call-2"][2] == "ok"
    assert by_id["call-2"][3] is False


def test_can_parallel_tool_swallows_risk_engine_failure(monkeypatch):
    engine = ChatEngine.__new__(ChatEngine)
    engine.config = {}
    engine.registry = SimpleNamespace(
        get=lambda name: SimpleNamespace(server_name="srv"),
    )

    def _explode(*args, **kwargs):
        raise RuntimeError("risk engine down")

    engine.risk_engine = SimpleNamespace(evaluate=_explode)
    assert engine._can_parallel_tool("some_mcp_tool", {}) is False


async def test_l2_dedupe_does_not_repeat_a_call_the_tool_emitted(monkeypatch):
    engine = ChatEngine.__new__(ChatEngine)
    engine.config = {}
    monkeypatch.setattr(engine, "_can_parallel_tool", lambda name, args: False)

    async def _emit_then_raise(**kwargs):
        await kwargs["ws"].send_json({
            "type": "chat.tool_call",
            "message_id": "msg-1",
            "conversation_id": "conv-1",
            "call_id": kwargs["call_id"],
            "tool": "run_command",
            "args": {},
            "risk": "SAFE",
        })
        raise RuntimeError("boom")

    monkeypatch.setattr(engine, "_execute_runtime_tool", _emit_then_raise)
    ws = _WS()

    results = await engine._execute_tool_calls(
        ws=ws,
        message_id="msg-1",
        conv_id="conv-1",
        client=None,
        model="",
        provider_id="",
        runtime=_runtime(),
        agent_id="agent-1",
        depth=0,
        tool_calls=[_call("call-1", "run_command")],
    )

    assert results[0][3] is True
    assert [e["type"] for e in ws.events] == ["chat.tool_call", "chat.tool_result"]
    assert ws.events[0]["call_id"] == "call-1"
    assert ws.events[1]["call_id"] == "call-1"


async def test_contained_error_text_is_redacted(monkeypatch):
    engine = ChatEngine.__new__(ChatEngine)
    engine.config = {}

    async def _raise(*args, **kwargs):
        raise RuntimeError("leaked sk-abcdefghijklmnopqrstuvwxyz123456")

    monkeypatch.setattr(engine, "_execute_guarded_inner", _raise)

    result = await engine._execute_guarded(
        _WS(), "msg-1", "call-1", "run_command", {}, "conv-1",
    )

    assert "[REDACTED:api_key_pattern]" in result
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in result

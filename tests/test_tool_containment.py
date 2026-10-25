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

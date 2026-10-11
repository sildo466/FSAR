# SPDX-License-Identifier: MIT
from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import src.server.chat_engine as ce
from src.memory.workspace import WorkspaceRepo
from src.security.command_classifier import CommandVerdict
from src.server.chat_engine import ChatEngine


class Config:
    def __init__(self):
        self.values = {"security.session.no_trust_mode": False}

    def get(self, key, default=None):
        return self.values.get(key, default)

    def patch(self, key, value):
        self.values[key] = value

    def save(self):
        pass


class WS:
    def __init__(self):
        self.messages = []

    async def send_json(self, message):
        self.messages.append(message)


def _engine(tmp_path: Path, monkeypatch, *, room: bool = True):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    item = object.__new__(ChatEngine)
    item.workspace_repo = WorkspaceRepo(tmp_path / "memory.db")
    item.config = Config()
    item.permissions = SimpleNamespace(no_trust_mode=False)

    async def _executed(*args, **kwargs):
        return "EXECUTED"

    item.registry = SimpleNamespace(
        get=lambda name: SimpleNamespace(server_name=None),
        execute=_executed,
    )
    item.workspace_gate = SimpleNamespace(
        validate_path=lambda *a, **k: SimpleNamespace(resolved_path="/w/x"),
        command_verdicts=lambda *a, **k: [],
    )
    item.risk_engine = SimpleNamespace(evaluate=lambda tool, args, **kw: SimpleNamespace(
        needs_confirm=lambda: False,
        is_denied=lambda: False,
        effective_risk="SAFE",
        reason="",
    ))

    async def _pass_sandbox(*args, **kwargs):
        return None

    monkeypatch.setattr(item, "_sandbox_tool_call", _pass_sandbox)
    monkeypatch.setattr(ce, "append_entry", lambda entry: None)

    row = item.workspace_repo.list()[0]
    item._room_sandbox_for = (lambda conv_id: row) if room else (lambda conv_id: None)
    return item


def _classifier(monkeypatch, judge):
    monkeypatch.setattr(
        ce, "CommandClassifier",
        lambda config: SimpleNamespace(enabled=True, judge=judge),
    )


def _guarded(item, args, name="run_command"):
    ws = WS()
    result = asyncio.run(
        item._execute_guarded(ws, "message", "call", name, args, "conv")
    )
    return result, ws


def test_a_dangerous_room_command_is_refused(tmp_path, monkeypatch):
    item = _engine(tmp_path, monkeypatch)

    async def _judge(**kwargs):
        return CommandVerdict(dangerous=True, reason="reaches outside the boundary")

    _classifier(monkeypatch, _judge)

    result, ws = _guarded(
        item, {"command": "cat /etc/passwd", "description": "read a config file"}
    )

    assert "BLOCKED" in result
    assert [m["type"] for m in ws.messages] == ["chat.tool_call", "chat.tool_result"]
    audit = item.workspace_repo.list_audit(conversation_id="conv")
    assert audit[0]["verdict"] == "classifier_blocked"


def test_a_safe_room_command_still_runs(tmp_path, monkeypatch):
    item = _engine(tmp_path, monkeypatch)
    seen = []

    async def _judge(**kwargs):
        seen.append(kwargs)
        return CommandVerdict(dangerous=False)

    _classifier(monkeypatch, _judge)

    result, _ = _guarded(
        item, {"command": "ls", "description": "list the workspace"}
    )

    assert result == "EXECUTED"
    assert seen[0]["intent"] == "list the workspace"
    assert seen[0]["tool"] == "run_command"


def test_an_unavailable_classifier_blocks(tmp_path, monkeypatch):
    item = _engine(tmp_path, monkeypatch)

    async def _judge(**kwargs):
        return CommandVerdict(
            dangerous=True, unavailable=True, reason="network down"
        )

    _classifier(monkeypatch, _judge)

    result, _ = _guarded(item, {"command": "ls", "description": "list"})

    assert "unavailable" in result
    audit = item.workspace_repo.list_audit(conversation_id="conv")
    assert audit[0]["verdict"] == "classifier_unavailable"


def test_a_missing_intent_is_refused_without_asking_the_classifier(tmp_path, monkeypatch):
    item = _engine(tmp_path, monkeypatch)

    async def _boom(**kwargs):
        raise AssertionError("an absent intent must not reach the model")

    _classifier(monkeypatch, _boom)

    result, _ = _guarded(item, {"command": "ls"})

    assert "BLOCKED" in result
    audit = item.workspace_repo.list_audit(conversation_id="conv")
    assert audit[0]["verdict"] == "classifier_blocked"


def test_a_non_room_turn_never_reaches_the_classifier(tmp_path, monkeypatch):
    item = _engine(tmp_path, monkeypatch, room=False)

    def _boom(config):
        raise AssertionError("the classifier must not be built outside a room")

    monkeypatch.setattr(ce, "CommandClassifier", _boom)

    result, _ = _guarded(item, {"command": "echo hi"})

    assert result == "EXECUTED"


def test_a_non_command_tool_is_not_classified(tmp_path, monkeypatch):
    item = _engine(tmp_path, monkeypatch)

    def _boom(config):
        raise AssertionError("only commands go through the classifier")

    monkeypatch.setattr(ce, "CommandClassifier", _boom)

    result, _ = _guarded(item, {"path": "."}, name="file_ops")

    assert result == "EXECUTED"


def test_a_disabled_switch_lets_the_command_through(tmp_path, monkeypatch):
    item = _engine(tmp_path, monkeypatch)
    monkeypatch.setattr(
        ce, "CommandClassifier",
        lambda config: SimpleNamespace(enabled=False),
    )

    result, _ = _guarded(item, {"command": "ls"})

    assert result == "EXECUTED"

# SPDX-License-Identifier: MIT
"""`fsar run` — one-shot headless agent turn."""

from __future__ import annotations

import json

import pytest

from src.cli import run as cli_run


def test_run_once_returns_conversation_conclusion_and_outcome(monkeypatch) -> None:
    monkeypatch.setattr(
        cli_run, "_spawn_headless_turn",
        lambda task, **kw: ("conv-1", "I have read the room.", "success"),
    )
    assert cli_run.run_once("say hello") == {
        "conversation_id": "conv-1",
        "conclusion": "I have read the room.",
        "outcome": "success",
    }


def test_run_once_forwards_task_and_conversation(monkeypatch) -> None:
    seen: dict[str, object] = {}

    def fake(task: str, **kwargs: object) -> tuple[str, str, str]:
        seen["task"] = task
        seen.update(kwargs)
        return ("conv-7", "ok", "success")

    monkeypatch.setattr(cli_run, "_spawn_headless_turn", fake)
    result = cli_run.run_once("hi", conversation_id="conv-7")
    assert seen == {"task": "hi", "conversation_id": "conv-7", "character_card_id": None}
    assert result["conversation_id"] == "conv-7"


def test_main_json_prints_one_object(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli_run, "run_once",
        lambda task, **kw: {
            "conversation_id": "conv-1", "conclusion": "done", "outcome": "success",
        },
    )
    assert cli_run.main(["say hello", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "conversation_id": "conv-1", "conclusion": "done", "outcome": "success",
    }


def test_main_plain_prints_conclusion_only(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli_run, "run_once",
        lambda task, **kw: {
            "conversation_id": "conv-1", "conclusion": "done", "outcome": "success",
        },
    )
    assert cli_run.main(["say hello"]) == 0
    assert capsys.readouterr().out.strip() == "done"


def test_main_exit_code_reflects_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        cli_run, "run_once",
        lambda task, **kw: {
            "conversation_id": "conv-1", "conclusion": "(Cancelled.)",
            "outcome": "failure",
        },
    )
    assert cli_run.main(["say hello"]) == 1


def test_main_requires_task() -> None:
    with pytest.raises(SystemExit):
        cli_run.main([])


@pytest.mark.asyncio
async def test_fresh_conversation_starts_and_binds_a_session(tmp_path) -> None:
    """Regression: `fsar run` without --conversation-id read `.session_id` off a
    SessionRow, which only carries `.id`, so the turn died before it began."""
    from src.core.agent_runtime import AgentLoopResult
    from src.server import chat_engine
    from src.server.chat_engine import ChatEngine
    from src.server.risk_bridge import RiskBridge
    from src.utils.fsar_config import FsarConfig

    config = FsarConfig(tmp_path / "fsar.yaml")
    config.patch("memory.sqlite_path", str(tmp_path / "memory.db"))
    config.save()
    engine = ChatEngine(config, RiskBridge())
    # Wire the singleton the way ws_server does, rather than stubbing the
    # lookup — stubbing it is what let the AttributeError ship.
    chat_engine.set_default_chat_engine(engine)
    engine.client_and_model = lambda: (object(), "fake-model", "fake-provider")

    seen: dict[str, str] = {}

    async def fake_run_agent(*, conv_id: str, **_: object) -> AgentLoopResult:
        seen["conv_id"] = conv_id
        return AgentLoopResult("read the room", "success")

    engine._run_agent = fake_run_agent

    try:
        conv_id, conclusion, outcome = await chat_engine.handle_user_agent_message_result(
            None, "say hello",
        )
    finally:
        chat_engine.set_default_chat_engine(None)

    assert conv_id
    assert conclusion == "read the room"
    assert outcome == "success"
    assert seen["conv_id"] == conv_id
    assert engine.session_store.get(conv_id) is not None
    assert engine.workspace_repo.get_binding(conv_id) is not None


def test_headless_engine_reuses_the_wired_instance(tmp_path) -> None:
    """The social bridge must land on the server's engine, not a second copy."""
    from src.server import chat_engine
    from src.server.chat_engine import ChatEngine
    from src.server.risk_bridge import RiskBridge
    from src.utils.fsar_config import FsarConfig

    config = FsarConfig(tmp_path / "fsar.yaml")
    config.patch("memory.sqlite_path", str(tmp_path / "memory.db"))
    config.save()
    wired = ChatEngine(config, RiskBridge())
    chat_engine.set_default_chat_engine(wired)
    try:
        assert chat_engine.headless_chat_engine() is wired
    finally:
        chat_engine.set_default_chat_engine(None)


def test_headless_engine_stands_alone_without_a_server(tmp_path, monkeypatch) -> None:
    """`fsar run` is its own process and never wires the singleton; it used to
    raise before the turn started."""
    from src.server import chat_engine
    from src.utils.fsar_config import FsarConfig

    config = FsarConfig(tmp_path / "fsar.yaml")
    config.patch("memory.sqlite_path", str(tmp_path / "memory.db"))
    config.save()
    monkeypatch.setattr(chat_engine, "_default_chat_engine", None)
    monkeypatch.setattr(chat_engine, "get_default_config", lambda: config)

    assert isinstance(chat_engine.headless_chat_engine(), chat_engine.ChatEngine)

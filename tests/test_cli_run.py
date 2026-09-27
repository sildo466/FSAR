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

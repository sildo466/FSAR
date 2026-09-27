# SPDX-License-Identifier: MIT
"""`fsar room` — the client half of the member ingress."""

from __future__ import annotations

import json
import urllib.error

import pytest

from src.cli import room as cli_room


def test_unreachable_server_reports_instead_of_raising(monkeypatch) -> None:
    def boom(*args, **kwargs):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(cli_room.urllib.request, "urlopen", boom)
    result = cli_room.say("hi", base_url="http://127.0.0.1:9", token="t")
    assert result["ok"] is False
    assert result["code"] == "unreachable"


def test_say_posts_content_with_bearer_token(monkeypatch) -> None:
    seen: dict[str, object] = {}

    def fake_post(url: str, payload: dict, token: str) -> dict:
        seen.update(url=url, payload=payload, token=token)
        return {"ok": True, "code": "ok", "row_id": 5}

    monkeypatch.setattr(cli_room, "_post_json", fake_post)
    result = cli_room.say("hello", base_url="http://127.0.0.1:8765", token="t")
    assert seen == {
        "url": "http://127.0.0.1:8765/api/room/member/message",
        "payload": {"content": "hello"},
        "token": "t",
    }
    assert result["row_id"] == 5


def test_read_passes_cursor(monkeypatch) -> None:
    seen: dict[str, object] = {}

    def fake_get(url: str, token: str) -> dict:
        seen.update(url=url, token=token)
        return {"messages": []}

    monkeypatch.setattr(cli_room, "_get_json", fake_get)
    cli_room.read(since=42, base_url="http://x", token="t")
    assert seen["url"] == "http://x/api/room/member/state?since=42"
    assert seen["token"] == "t"


def test_main_reads_token_from_env(monkeypatch, capsys) -> None:
    monkeypatch.setenv("FSAR_ROOM_TOKEN", "env-token")
    monkeypatch.setattr(
        cli_room, "say",
        lambda text, **kw: {"ok": True, "code": "ok", "row_id": 1},
    )
    assert cli_room.main(["say", "hi"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_main_accepts_the_token_after_the_subcommand(monkeypatch, capsys) -> None:
    seen: dict[str, object] = {}

    def fake_say(text, *, base_url, token):
        seen.update(text=text, base_url=base_url, token=token)
        return {"ok": True, "code": "ok", "row_id": 1}

    monkeypatch.delenv("FSAR_ROOM_TOKEN", raising=False)
    monkeypatch.setattr(cli_room, "say", fake_say)
    assert cli_room.main(["say", "hi", "--token", "t2", "--url", "http://y"]) == 0
    assert seen == {"text": "hi", "base_url": "http://y", "token": "t2"}


def test_main_needs_a_token(monkeypatch, capsys) -> None:
    monkeypatch.delenv("FSAR_ROOM_TOKEN", raising=False)
    with pytest.raises(SystemExit):
        cli_room.main(["say", "hi"])
    assert "FSAR_ROOM_TOKEN" in capsys.readouterr().err


def test_main_unknown_subcommand_exits(monkeypatch) -> None:
    monkeypatch.setenv("FSAR_ROOM_TOKEN", "t")
    with pytest.raises(SystemExit):
        cli_room.main(["dance"])


def test_main_exit_code_reflects_rejection(monkeypatch, capsys) -> None:
    monkeypatch.setenv("FSAR_ROOM_TOKEN", "t")
    monkeypatch.setattr(
        cli_room, "say",
        lambda text, **kw: {"ok": False, "code": "muted", "row_id": None},
    )
    assert cli_room.main(["say", "hi"]) == 1
    assert json.loads(capsys.readouterr().out)["code"] == "muted"


def test_main_read_prints_the_state(monkeypatch, capsys) -> None:
    monkeypatch.setenv("FSAR_ROOM_TOKEN", "t")
    monkeypatch.setattr(
        cli_room, "read",
        lambda **kw: {"messages": [{"row_id": 1, "content": "hi"}]},
    )
    assert cli_room.main(["read", "--since", "7"]) == 0
    assert json.loads(capsys.readouterr().out)["messages"][0]["row_id"] == 1

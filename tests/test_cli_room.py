# SPDX-License-Identifier: MIT
"""`fsar room` — the client a member runs, talking to the LAN room API."""

from __future__ import annotations

import io
import json
import ssl
import urllib.error

import pytest

from src.cli import room as cli_room


def test_the_default_base_url_is_the_lan_api() -> None:
    assert cli_room.DEFAULT_BASE_URL == "https://127.0.0.1:8766"


def test_the_parser_accepts_insecure_and_a_room_id() -> None:
    args = cli_room.build_parser().parse_args(
        ["say", "hi", "--insecure", "--room-id", "4", "--key", "k"]
    )
    assert args.insecure is True
    assert args.room_id == 4
    assert args.key == "k"


def test_insecure_is_off_by_default() -> None:
    assert cli_room.build_parser().parse_args(["say", "hi"]).insecure is False


def test_a_verified_context_is_left_to_urllib() -> None:
    assert cli_room._ssl_context(False) is None


def test_an_insecure_context_stops_verifying() -> None:
    context = cli_room._ssl_context(True)
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_NONE
    assert context.check_hostname is False


def test_a_tls_failure_explains_itself(monkeypatch) -> None:
    def refuse(*args, **kwargs):
        raise ssl.SSLCertVerificationError("self-signed certificate")

    monkeypatch.setattr(cli_room.urllib.request, "urlopen", refuse)
    result = cli_room.say("hi", base_url="https://192.168.1.20:8766", token="t")
    assert result["ok"] is False
    assert result["code"] == "tls_error"
    assert "--insecure" in result["hint"]


def test_an_insecure_call_passes_the_context_through(monkeypatch) -> None:
    seen: dict = {}

    def capture(request, timeout=None, context=None):
        seen["context"] = context
        seen["url"] = request.full_url

        class _Response:
            def read(self) -> bytes:
                return b'{"rooms": [{"room_id": 3}]}'

            def __enter__(self):
                return self

            def __exit__(self, *exc) -> bool:
                return False

        return _Response()

    monkeypatch.setattr(cli_room.urllib.request, "urlopen", capture)
    cli_room.say(
        "hi", base_url="https://192.168.1.20:8766", token="t", insecure=True,
    )
    assert isinstance(seen["context"], ssl.SSLContext)


def test_say_asks_for_the_room_then_posts_to_it() -> None:
    seen: dict = {}

    def fake_get(url: str, token: str, **kw) -> dict:
        seen["index_url"] = url
        return {"rooms": [{"room_id": 7}]}

    def fake_post(url: str, payload: dict, token: str, **kw) -> dict:
        seen.update(post_url=url, payload=payload, headers=kw.get("headers"))
        return {"row_id": 12}

    monkey = pytest.MonkeyPatch()
    monkey.setattr(cli_room, "_get_json", fake_get)
    monkey.setattr(cli_room, "_post_json", fake_post)
    result = cli_room.say("hello", base_url="https://a:8766", token="t")
    monkey.undo()

    assert seen["index_url"] == "https://a:8766/room/index"
    assert seen["post_url"] == "https://a:8766/room/7/messages"
    assert seen["payload"] == {"content": "hello"}
    assert seen["headers"]["Idempotency-Key"]
    assert result == {"row_id": 12}


def test_an_explicit_room_id_skips_the_lookup() -> None:
    calls: list[str] = []

    def fake_get(url: str, token: str, **kw) -> dict:
        calls.append(url)
        return {}

    monkey = pytest.MonkeyPatch()
    monkey.setattr(cli_room, "_get_json", fake_get)
    monkey.setattr(cli_room, "_post_json", lambda url, payload, token, **kw: {"row_id": 1})
    cli_room.say("hi", base_url="https://a:8766", token="t", room_id=9)
    monkey.undo()
    assert calls == []


def test_a_given_key_is_reused_so_a_retry_is_safe() -> None:
    seen: dict = {}
    monkey = pytest.MonkeyPatch()
    monkey.setattr(cli_room, "_resolve_room", lambda **kw: (1, None))
    monkey.setattr(
        cli_room, "_post_json",
        lambda url, payload, token, **kw: seen.update(kw.get("headers")) or {},
    )
    cli_room.say("hi", base_url="https://a:8766", token="t", key="same-key")
    monkey.undo()
    assert seen == {"Idempotency-Key": "same-key"}


def test_say_reports_a_credential_that_names_no_room() -> None:
    monkey = pytest.MonkeyPatch()
    monkey.setattr(cli_room, "_get_json", lambda url, token, **kw: {"rooms": []})
    result = cli_room.say("hi", base_url="https://a:8766", token="t")
    monkey.undo()
    assert result["ok"] is False
    assert result["code"] == "no_room"


def test_read_gets_the_state_for_the_resolved_room() -> None:
    seen: dict = {}
    monkey = pytest.MonkeyPatch()
    monkey.setattr(cli_room, "_resolve_room", lambda **kw: (5, None))
    monkey.setattr(
        cli_room, "_get_json",
        lambda url, token, **kw: seen.update(url=url) or {"messages": []},
    )
    result = cli_room.read(since=42, base_url="https://a:8766", token="t")
    monkey.undo()
    assert seen["url"] == "https://a:8766/room/5/state?since=42"
    assert result == {"messages": []}


def test_read_reports_a_credential_that_names_no_room() -> None:
    monkey = pytest.MonkeyPatch()
    monkey.setattr(cli_room, "_get_json", lambda url, token, **kw: {})
    result = cli_room.read(base_url="https://a:8766", token="t")
    monkey.undo()
    assert result["code"] == "no_room"


def test_a_rejection_surfaces_the_servers_code(monkeypatch) -> None:
    def refuse(request, timeout=None, context=None):
        raise urllib.error.HTTPError(
            request.full_url, 403, "Forbidden", {},
            io.BytesIO(b'{"detail": "muted", "request_id": "req-1"}'),
        )

    monkeypatch.setattr(cli_room, "_resolve_room", lambda **kw: (1, None))
    monkeypatch.setattr(cli_room.urllib.request, "urlopen", refuse)
    result = cli_room.say("hi", base_url="https://a:8766", token="t")
    assert result["ok"] is False
    assert result["code"] == "muted"
    assert result["request_id"] == "req-1"


def test_a_rejection_without_a_body_still_reports_a_code(monkeypatch) -> None:
    def refuse(request, timeout=None, context=None):
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr(cli_room, "_resolve_room", lambda **kw: (1, None))
    monkeypatch.setattr(cli_room.urllib.request, "urlopen", refuse)
    result = cli_room.say("hi", base_url="https://a:8766", token="t")
    assert result["code"] == "http_401"


def test_an_unreachable_server_is_reported_not_raised(monkeypatch) -> None:
    def boom(*args, **kwargs):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(cli_room, "_resolve_room", lambda **kw: (1, None))
    monkeypatch.setattr(cli_room.urllib.request, "urlopen", boom)
    result = cli_room.say("hi", base_url="https://127.0.0.1:9", token="t")
    assert result["ok"] is False
    assert result["code"] == "unreachable"


def test_a_failed_lookup_is_not_reported_as_a_bad_credential(monkeypatch) -> None:
    """A certificate or connectivity problem must not read as "no room"."""
    def boom(*args, **kwargs):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(cli_room.urllib.request, "urlopen", boom)
    result = cli_room.say("hi", base_url="https://127.0.0.1:9", token="t")
    assert result["code"] == "unreachable"


def test_main_reads_the_token_from_the_env(monkeypatch, capsys) -> None:
    monkeypatch.setenv("FSAR_ROOM_TOKEN", "env-token")
    monkeypatch.setattr(
        cli_room, "say", lambda text, **kw: {"row_id": 1},
    )
    assert cli_room.main(["say", "hi"]) == 0
    assert json.loads(capsys.readouterr().out) == {"row_id": 1}


def test_main_needs_a_token(monkeypatch, capsys) -> None:
    monkeypatch.delenv("FSAR_ROOM_TOKEN", raising=False)
    with pytest.raises(SystemExit):
        cli_room.main(["say", "hi"])
    assert "FSAR_ROOM_TOKEN" in capsys.readouterr().err


def test_main_rejects_an_unknown_subcommand(monkeypatch) -> None:
    monkeypatch.setenv("FSAR_ROOM_TOKEN", "t")
    with pytest.raises(SystemExit):
        cli_room.main(["dance"])


def test_main_exit_code_reflects_a_rejection(monkeypatch, capsys) -> None:
    monkeypatch.setenv("FSAR_ROOM_TOKEN", "t")
    monkeypatch.setattr(
        cli_room, "say",
        lambda text, **kw: {"ok": False, "code": "muted", "row_id": None},
    )
    assert cli_room.main(["say", "hi"]) == 1
    assert json.loads(capsys.readouterr().out)["code"] == "muted"


def test_main_passes_the_flags_through(monkeypatch) -> None:
    seen: dict = {}
    monkeypatch.setenv("FSAR_ROOM_TOKEN", "t")

    def fake_say(text, **kw):
        seen.update(text=text, **kw)
        return {"row_id": 1}

    monkeypatch.setattr(cli_room, "say", fake_say)
    cli_room.main([
        "say", "hi", "--url", "https://b:9000", "--insecure",
        "--room-id", "3", "--key", "k",
    ])
    assert seen == {
        "text": "hi", "base_url": "https://b:9000", "token": "t",
        "insecure": True, "room_id": 3, "key": "k",
    }


def test_main_read_prints_the_state(monkeypatch, capsys) -> None:
    monkeypatch.setenv("FSAR_ROOM_TOKEN", "t")
    monkeypatch.setattr(
        cli_room, "read",
        lambda **kw: {"messages": [{"row_id": 1, "content": "hi"}]},
    )
    assert cli_room.main(["read", "--since", "7"]) == 0
    assert json.loads(capsys.readouterr().out)["messages"][0]["row_id"] == 1

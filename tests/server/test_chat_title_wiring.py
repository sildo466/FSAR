# SPDX-License-Identifier: Apache-2.0
"""Every chat mode must hand the finished turn to the title generator.

Regression: character mode (and agent mode on a tier with post_reflection
off) never called _maybe_title, so those sessions stayed untitled forever.
"""
from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from src.core.agent_tiers import get_tier_profile
from src.memory.session_store import SessionStore
import src.server.chat_engine as ce
import src.server.ws_server as ws_mod


def _resp(content: str | None = None):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(
            content=content, tool_calls=None,
        ))],
        usage={"prompt_tokens": 10, "completion_tokens": 3, "cached_tokens": 0},
    )


def _stream(*a, **k):
    return iter([
        SimpleNamespace(choices=[SimpleNamespace(
            delta=SimpleNamespace(content="hi", tool_calls=None))]),
    ])


def _collect(ws, limit=80):
    for _ in range(limit):
        if ws.receive_json().get("type") == "chat.done":
            return


class _Spy:
    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    def schedule(self, conv_id: str, first_message: str) -> None:
        self.calls.append((conv_id, first_message))


def _setup(monkeypatch, tmp_path, tier: str = "low"):
    engine = ws_mod._engine
    monkeypatch.setattr(engine, "session_store", SessionStore(str(tmp_path / "m.db")))
    spy = _Spy()
    monkeypatch.setattr(engine, "title_generator", spy)
    monkeypatch.setattr(ce, "get_tier_profile", lambda name: get_tier_profile(tier))
    monkeypatch.setattr(engine, "client_and_model", lambda: (object(), "model-x", "prov"))
    monkeypatch.setattr(engine, "_reflect", lambda *a, **k: None)
    return spy


def _send(ws, text: str, mode: str) -> None:
    ws.receive_json()
    ws.send_json({"type": "chat.send", "content": text, "mode": mode})
    _collect(ws)


def test_character_mode_schedules_title(monkeypatch, tmp_path):
    spy = _setup(monkeypatch, tmp_path)
    monkeypatch.setattr(ce, "chat_completion", lambda *a, **k: _resp(content="hello!"))
    with TestClient(ws_mod.app).websocket_connect("/ws") as ws:
        _send(ws, "hi there", "character")
    assert len(spy.calls) == 1, f"character mode never scheduled a title: {spy.calls}"
    assert spy.calls[0][1] == "hi there"


def test_agent_mode_titles_even_when_reflection_is_off(monkeypatch, tmp_path):
    spy = _setup(monkeypatch, tmp_path, tier="low")
    monkeypatch.setattr(ce, "chat_completion", lambda *a, **k: _resp(content="hello!"))
    with TestClient(ws_mod.app).websocket_connect("/ws") as ws:
        _send(ws, "hi there", "agent")
    assert len(spy.calls) == 1, f"agent/low mode never scheduled a title: {spy.calls}"


def test_companion_mode_schedules_title(monkeypatch, tmp_path):
    spy = _setup(monkeypatch, tmp_path)
    monkeypatch.setattr(ce, "chat_completion", _stream)
    with TestClient(ws_mod.app).websocket_connect("/ws") as ws:
        _send(ws, "hi there", "companion")
    assert len(spy.calls) == 1, f"companion mode never scheduled a title: {spy.calls}"

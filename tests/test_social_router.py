import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.server.chat_engine import handle_user_message
from src.social.channels import ChannelEvent, ReplyTarget
from src.social.router import ChannelRouter


@pytest.mark.asyncio
async def test_router_handle_routes_through_outbox(tmp_path, monkeypatch):
    captured = []
    persisted = []
    handled = []

    class _FakeAdapter:
        name = "telegram"

        async def start(self, router):
            return None

        async def stop(self):
            return None

        async def send(self, target, text):
            captured.append((target.peer_id, text))

    monkeypatch.setattr(
        "src.social.outbox._JOURNAL_PATH",
        tmp_path / "outbox.jsonl",
    )
    monkeypatch.setattr("src.social.router.is_muted", lambda platform, peer: False)
    monkeypatch.setattr("src.social.router.upsert_binding", lambda *args, **kwargs: None)
    monkeypatch.setattr("src.social.router.touch_binding", lambda *args: None)
    monkeypatch.setattr(
        "src.social.router.load_or_create_session",
        lambda platform, peer: "session-42",
    )
    monkeypatch.setattr(
        "src.social.router.load_session_messages",
        lambda session_id: [{"role": "assistant", "content": "before"}],
    )
    monkeypatch.setattr(
        "src.social.router.append_session_message",
        lambda session_id, role, content: persisted.append((session_id, role, content)),
    )

    def reply(session_id, text, *, session_messages, **overrides):
        handled.append((session_id, text, session_messages))
        return f"echo:{text}"

    monkeypatch.setattr(
        "src.social.router.handle_user_message",
        reply,
    )

    router = ChannelRouter()
    router.register(_FakeAdapter())
    await router.start_outbox()
    event = ChannelEvent(
        platform="telegram",
        peer_id="42",
        peer_kind="dm",
        message_id="100",
        text="hi",
        sent_at=datetime.now(timezone.utc),
        reply_target=ReplyTarget(platform="telegram", peer_id="42"),
    )

    await router.handle(event)
    await asyncio.sleep(0.1)
    await router.stop_outbox()

    assert captured == [("42", "echo:hi")]
    assert handled == [
        ("session-42", "hi", [{"role": "assistant", "content": "before"}])
    ]
    assert persisted == [
        ("session-42", "user", "hi"),
        ("session-42", "assistant", "echo:hi"),
    ]


@pytest.mark.asyncio
async def test_router_drops_muted_peer(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "src.social.outbox._JOURNAL_PATH",
        tmp_path / "outbox.jsonl",
    )
    monkeypatch.setattr("src.social.router.is_muted", lambda platform, peer: True)
    called = False

    def handle_message(session_id, text):
        nonlocal called
        called = True
        return text

    monkeypatch.setattr("src.social.router.handle_user_message", handle_message)

    router = ChannelRouter()
    event = ChannelEvent(
        platform="telegram",
        peer_id="42",
        peer_kind="dm",
        message_id="100",
        text="hi",
        sent_at=datetime.now(timezone.utc),
        reply_target=ReplyTarget(platform="telegram", peer_id="42"),
    )
    await router.handle(event)

    assert called is False


def test_handle_user_message_calls_configured_model(monkeypatch):
    class Config:
        chat_default_model = {
            "kind": "model",
            "provider": "provider-1",
            "model": "model-1",
        }
        memory_sqlite_path = "unused.db"

        def get(self, key, default=None):
            return default

        def get_llm_config(self, provider_id):
            assert provider_id == "provider-1"
            return {"model": "model-1", "max_output_tokens": 512}

    captured = {}
    monkeypatch.setattr("src.server.chat_engine.get_default_config", lambda: Config())
    monkeypatch.setattr("src.server.chat_engine.CardRepo", lambda path: SimpleNamespace(
        get_character=lambda card_id: None,
        get_default_character=lambda: SimpleNamespace(),
        get_default_user_card=lambda: None,
    ))
    monkeypatch.setattr("src.server.chat_engine.SessionStore", lambda path: SimpleNamespace(
        get_character=lambda session_id: None,
    ))
    monkeypatch.setattr("src.server.chat_engine.build_system_prompt", lambda **kwargs: "system")
    monkeypatch.setattr("src.server.chat_engine.make_llm_client", lambda provider_id: object())

    def complete(client, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="real reply"))]
        )

    monkeypatch.setattr("src.server.chat_engine.cached_chat_completion", complete)
    history = [{"role": "assistant", "content": "earlier"}]

    reply = handle_user_message("session-42", "hello", session_messages=history)

    assert reply == "real reply"
    assert captured["provider_id"] == "provider-1"
    assert captured["model"] == "model-1"
    assert captured["messages"] == [
        {"role": "system", "content": "system"},
        {"role": "assistant", "content": "earlier"},
        {"role": "user", "content": "hello"},
    ]

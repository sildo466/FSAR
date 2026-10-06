# SPDX-License-Identifier: MIT
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from src.server.chat_engine import ChatEngine


class FakeWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send_json(self, message: dict) -> None:
        self.messages.append(message)


def _engine() -> ChatEngine:
    engine = object.__new__(ChatEngine)
    engine._cancelled = False
    return engine


def _card_repo(written: dict) -> SimpleNamespace:
    return SimpleNamespace(
        get_character=lambda cid: SimpleNamespace(id=cid, name="Mira",
                                                 tts_autoplay_on_card=1),
        get_default_character=lambda: SimpleNamespace(id=1, name="FSAR"),
        get_emotion_schema=lambda cid: [
            {"key": "mood", "min": 0.0, "max": 1.0, "initial": 0.0},
        ],
        get_emotion_formulas=lambda cid: {"mood": "mood + 1"},
        get_emotion_state=lambda cid: {"mood": 0.0},
        set_emotion_state=lambda cid, state: written.update(
            {"character_id": cid, "state": state}
        ),
    )


def test_emotion_pass_uses_explicit_character() -> None:
    engine = _engine()
    engine.session_store = SimpleNamespace(get_character=lambda cid: None)
    written: dict = {}
    engine.card_repo = _card_repo(written)

    result = ChatEngine._post_turn_emotion_pass(engine, "group-session", char_id=9)

    assert result == {"mood": 1.0}
    assert written["character_id"] == 9


def test_emotion_pass_falls_back_to_session_character() -> None:
    engine = _engine()
    engine.session_store = SimpleNamespace(get_character=lambda cid: 4)
    written: dict = {}
    engine.card_repo = _card_repo(written)

    ChatEngine._post_turn_emotion_pass(engine, "solo-session")

    assert written["character_id"] == 4


def test_tts_autoplay_reads_explicit_character() -> None:
    engine = _engine()
    engine.config = {"tts.active": "edge", "tts.autoplay": True}
    engine.session_store = SimpleNamespace(get_character=lambda cid: None)
    engine.card_repo = SimpleNamespace(
        get_character=lambda cid: SimpleNamespace(id=cid, tts_autoplay_on_card=1)
    )
    ws = FakeWebSocket()

    asyncio.run(
        ChatEngine._maybe_queue_tts(
            engine, ws, message_id="m1", text="hello",
            conversation_id="group-session", character_id=9,
        )
    )

    assert any(m["type"] == "tts.synthesize_queued" for m in ws.messages)


def test_explicit_speaker_honours_per_card_autoplay_opt_out() -> None:
    """The speaker's own card can opt out of autoplay; only the explicit
    character_id lets a group room see that opt-out."""
    engine = _engine()
    engine.config = {"tts.active": "edge", "tts.autoplay": True}
    engine.session_store = SimpleNamespace(get_character=lambda cid: None)
    engine.card_repo = SimpleNamespace(
        get_character=lambda cid: SimpleNamespace(id=cid, tts_autoplay_on_card=0)
    )
    ws = FakeWebSocket()

    asyncio.run(
        ChatEngine._maybe_queue_tts(
            engine, ws, message_id="m1", text="hello",
            conversation_id="group-session", character_id=9,
        )
    )

    assert not any(m["type"] == "tts.synthesize_queued" for m in ws.messages)


def test_tts_falls_back_to_global_config_for_unknown_character() -> None:
    engine = _engine()
    engine.config = {"tts.active": "edge", "tts.autoplay": True}
    engine.session_store = SimpleNamespace(get_character=lambda cid: None)
    engine.card_repo = SimpleNamespace(get_character=lambda cid: None)
    ws = FakeWebSocket()

    asyncio.run(
        ChatEngine._maybe_queue_tts(
            engine, ws, message_id="m1", text="hello",
            conversation_id="group-session",
        )
    )

    assert any(m["type"] == "tts.synthesize_queued" for m in ws.messages)


def test_rate_records_against_explicit_session() -> None:
    engine = _engine()
    engine._msg_ids = {}
    engine._active_conv_id = "solo-session"
    engine.user_model = SimpleNamespace(record_pattern=lambda *a, **k: None)
    recorded: dict = {}
    engine.feedback = SimpleNamespace(
        add_or_update_rating=lambda **kw: recorded.update(kw)
    )

    result = ChatEngine.rate(engine, "12", 5, "spot on", session_id="group-session")

    assert result["status"] == "ok"
    assert recorded["message_id"] == 12
    assert recorded["session_id"] == "group-session"
    assert recorded["rating"] == 5


def test_rate_falls_back_to_active_conversation() -> None:
    engine = _engine()
    engine._msg_ids = {}
    engine._active_conv_id = "solo-session"
    engine.user_model = SimpleNamespace(record_pattern=lambda *a, **k: None)
    recorded: dict = {}
    engine.feedback = SimpleNamespace(
        add_or_update_rating=lambda **kw: recorded.update(kw)
    )

    ChatEngine.rate(engine, "12", 4)

    assert recorded["session_id"] == "solo-session"


def test_rate_reports_unknown_message() -> None:
    engine = _engine()
    engine._msg_ids = {}
    engine._active_conv_id = "solo-session"
    engine.feedback = SimpleNamespace(add_or_update_rating=lambda **kw: None)

    assert ChatEngine.rate(engine, "not-a-number", 3)["status"] == "no_message"

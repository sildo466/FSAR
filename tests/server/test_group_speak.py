# SPDX-License-Identifier: MIT
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from src.memory.cards import CharacterCard
from src.memory.rooms import Room
from src.server.group_engine import GroupEngine


class FakeWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send_json(self, message: dict) -> None:
        self.messages.append(message)


class DeadWebSocket:
    async def send_json(self, message: dict) -> None:
        raise RuntimeError("socket closed")


def _character(char_id: int = 7, name: str = "Mira") -> CharacterCard:
    return CharacterCard(
        id=char_id,
        name=name,
        description="A traveling witch.",
        personality="Calm and sharp.",
        scenario="In a room with the user.",
    )


def _chat() -> SimpleNamespace:
    chat = SimpleNamespace()
    chat._short_cache = {}
    chat._cancelled = False
    chat._msg_ids = {}
    chat.saved: list[dict] = []
    chat.prompts: list[str] = []
    chat.tts: list[dict] = []
    chat._model_thinking_effort = lambda: "off"

    chat._ensure_short = lambda conv_id: chat._short_cache.setdefault(conv_id, [])
    chat.client_and_model = lambda: (SimpleNamespace(base_url=""), "m", "p")
    chat._active_provider_family = lambda: "openai"
    chat._memory_block = lambda query, **kw: "- user likes tea"
    chat._model_limits = lambda: (128000, 100000)

    def save_assistant(message_id, conv_id, content, character_id=None):
        chat.saved.append({
            "message_id": message_id, "conv_id": conv_id,
            "content": content, "character_id": character_id,
        })
        chat._msg_ids[message_id] = 900 + len(chat.saved)

    chat._save_assistant = save_assistant
    chat.session_store = SimpleNamespace(
        update_message=lambda row_id, content, character_card_id=None: True,
    )

    async def stream_one_reply(ws, **kwargs):
        chat.prompts.append(kwargs["messages"][0]["content"])
        chat.stream_kwargs = kwargs
        await ws.send_json({
            "type": "chat.delta",
            "message_id": kwargs["message_id"],
            "conversation_id": kwargs["conv_id"],
            "content": "I know this place.",
            "character_id": getattr(kwargs.get("character"), "id", None),
            "character_name": kwargs.get("char_name"),
        })
        return "I know this place."

    chat._stream_one_reply = stream_one_reply

    chat._post_turn_emotion_pass = lambda conv_id, char_id=None: {"mood": 0.5}

    async def maybe_queue_tts(ws, **kwargs):
        chat.tts.append(kwargs)

    chat._maybe_queue_tts = maybe_queue_tts
    return chat


def _room() -> Room:
    return Room(id=1, name="Island", session_id="room-session",
                scenario_prompt="We must survive.")


def _engine(chat) -> GroupEngine:
    rooms = SimpleNamespace(members=lambda room_id: [7, 8])
    return GroupEngine(chat, rooms)


def _speak(engine, ws, character=None, should_stop=None):
    return asyncio.run(GroupEngine.speak(
        engine, ws,
        room=_room(),
        character=character or _character(),
        user_card=None,
        history=[],
        user_input="look around",
        should_stop=should_stop or (lambda: False),
    ))


def test_speak_returns_message_id_and_text() -> None:
    message_id, text = _speak(_engine(_chat()), FakeWebSocket())
    assert message_id.startswith("group_")
    assert text == "I know this place."


def test_speak_saves_with_speaker_id() -> None:
    chat = _chat()
    message_id, _ = _speak(_engine(chat), FakeWebSocket())
    assert chat.saved == [{
        "message_id": message_id,
        "conv_id": "room-session",
        "content": "I know this place.",
        "character_id": 7,
    }]


def test_speak_emits_speaker_start_delta_and_done() -> None:
    ws = FakeWebSocket()
    _speak(_engine(_chat()), ws)
    kinds = [m["type"] for m in ws.messages]
    assert kinds == ["group.speaker.start", "group.speaker.delta",
                     "group.speaker.done"]
    start = ws.messages[0]
    assert start["room_id"] == 1
    assert start["character_id"] == 7
    assert start["character_name"] == "Mira"
    assert ws.messages[-1]["emotion_state"] == {"mood": 0.5}


def test_speak_reports_the_row_id_so_a_fresh_reply_can_be_regenerated() -> None:
    """Regenerate addresses DB rows; a live message has no row id until the
    server reports one, so without this the button would do nothing."""
    ws = FakeWebSocket()
    _speak(_engine(_chat()), ws)
    done = next(m for m in ws.messages if m["type"] == "group.speaker.done")
    assert isinstance(done["row_id"], int)


def test_speak_replaces_in_place_when_asked() -> None:
    """A regenerate must rewrite the row rather than append a second copy."""
    chat = _chat()
    updated: list[dict] = []
    chat.session_store = SimpleNamespace(
        update_message=lambda row_id, content, character_card_id=None: (
            updated.append({
                "row_id": row_id, "content": content,
                "character_card_id": character_card_id,
            }) or True
        ),
    )
    ws = FakeWebSocket()

    message_id, text = asyncio.run(GroupEngine.speak(
        _engine(chat), ws,
        room=_room(), character=_character(), user_card=None,
        history=[], user_input="look around", should_stop=lambda: False,
        message_id="42", replace_row_id=42,
    ))

    assert chat.saved == [], "replace must not append a new row"
    assert updated == [{
        "row_id": 42, "content": text, "character_card_id": 7,
    }]
    assert message_id == "42"
    done = next(m for m in ws.messages if m["type"] == "group.speaker.done")
    assert done["message_id"] == "42"
    assert done["row_id"] == 42


def test_speak_falls_back_to_append_when_the_row_is_gone() -> None:
    chat = _chat()
    chat.session_store = SimpleNamespace(
        update_message=lambda row_id, content, character_card_id=None: False,
    )
    ws = FakeWebSocket()

    asyncio.run(GroupEngine.speak(
        _engine(chat), ws,
        room=_room(), character=_character(), user_card=None,
        history=[], user_input="hi", should_stop=lambda: False,
        message_id="42", replace_row_id=42,
    ))

    assert len(chat.saved) == 1, "the reply should survive a vanished row"


def test_group_events_carry_no_chat_namespace() -> None:
    """Group stream must not leak chat.* events into the single-chat store."""
    ws = FakeWebSocket()
    _speak(_engine(_chat()), ws)
    assert not any(m["type"].startswith("chat.") for m in ws.messages)


def test_speak_passes_room_scene_and_tools_disabled() -> None:
    chat = _chat()
    _speak(_engine(chat), FakeWebSocket())
    system_prompt = chat.prompts[0]
    assert "<room_scene>" in system_prompt
    assert "We must survive." in system_prompt
    assert "`router`" not in system_prompt


def test_speak_includes_memory_block_and_history() -> None:
    chat = _chat()
    engine = _engine(chat)
    ws = FakeWebSocket()
    asyncio.run(GroupEngine.speak(
        engine, ws,
        room=_room(), character=_character(), user_card=None,
        history=[{"role": "assistant", "content": "[Kai]: watch out"}],
        user_input="look around",
        should_stop=lambda: False,
    ))
    messages = chat.stream_kwargs["messages"]
    assert "- user likes tea" in messages[0]["content"]
    assert messages[1] == {"role": "assistant", "content": "[Kai]: watch out"}
    assert messages[2] == {"role": "user", "content": "look around"}


def test_speak_forwards_max_output_and_stop_predicate() -> None:
    chat = _chat()
    stop = lambda: False  # noqa: E731
    _speak(_engine(chat), FakeWebSocket(), should_stop=stop)
    assert chat.stream_kwargs["max_output"] > 0
    assert chat.stream_kwargs["should_stop"] is stop
    assert chat.stream_kwargs["character"].id == 7
    assert chat.stream_kwargs["char_name"] == "Mira"


def test_speak_queues_tts_with_speaker_voice() -> None:
    chat = _chat()
    _speak(_engine(chat), FakeWebSocket())
    assert chat.tts[0]["character_id"] == 7
    assert chat.tts[0]["conversation_id"] == "room-session"
    assert chat.tts[0]["text"] == "I know this place."


def test_speak_survives_a_dead_socket() -> None:
    chat = _chat()
    message_id, text = _speak(_engine(chat), DeadWebSocket())
    assert message_id.startswith("group_")
    assert text == "I know this place."
    assert chat.saved[0]["character_id"] == 7


def test_speak_drops_a_blank_reply(monkeypatch) -> None:
    """An empty call must not leave a blank bubble or an empty memory turn."""
    chat = _chat()
    emotions: list = []
    chat._post_turn_emotion_pass = lambda conv_id, char_id=None: (
        emotions.append(char_id) or None
    )

    async def blank_stream(ws, **kwargs):
        return ""

    chat._stream_one_reply = blank_stream
    ws = FakeWebSocket()

    message_id, text = asyncio.run(GroupEngine.speak(
        _engine(chat), ws,
        room=_room(), character=_character(), user_card=None,
        history=[], user_input="hi", should_stop=lambda: False,
    ))

    assert text == ""
    assert chat.saved == [], "a blank reply must not be persisted"
    assert emotions == [], "no generation means no emotion update"
    assert chat.tts == [], "nothing to speak"
    done = ws.messages[-1]
    assert done["type"] == "group.speaker.done"
    assert done["failed"] is True


def test_speak_drops_a_reply_that_is_only_the_speaker_marker() -> None:
    chat = _chat()

    async def marker_only_stream(ws, **kwargs):
        return "[Mira]:   "

    chat._stream_one_reply = marker_only_stream
    ws = FakeWebSocket()

    _, text = asyncio.run(GroupEngine.speak(
        _engine(chat), ws,
        room=_room(), character=_character(), user_card=None,
        history=[], user_input="hi", should_stop=lambda: False,
    ))

    assert text == ""
    assert chat.saved == []
    assert ws.messages[-1]["failed"] is True


def test_blank_regenerate_leaves_the_original_row_alone() -> None:
    """Losing a good reply to a failed regeneration would be worse than
    leaving the old text in place."""
    chat = _chat()
    updates: list = []
    chat.session_store = SimpleNamespace(
        update_message=lambda row_id, content, character_card_id=None: (
            updates.append(content) or True
        ),
    )

    async def blank_stream(ws, **kwargs):
        return ""

    chat._stream_one_reply = blank_stream
    ws = FakeWebSocket()

    asyncio.run(GroupEngine.speak(
        _engine(chat), ws,
        room=_room(), character=_character(), user_card=None,
        history=[], user_input="hi", should_stop=lambda: False,
        message_id="42", replace_row_id=42,
    ))

    assert updates == [], "the original row must survive a failed regenerate"


def test_cancel_marks_room() -> None:
    engine = _engine(_chat())
    assert engine.is_cancelled(1) is False
    GroupEngine.cancel(engine, 1)
    assert engine.is_cancelled(1) is True
    GroupEngine.clear_cancel(engine, 1)
    assert engine.is_cancelled(1) is False

# SPDX-License-Identifier: MIT
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from src.memory.cards import CharacterCard
from src.memory.session_store import MessageRow
from src.server.group_engine import GroupEngine


class FakeWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send_json(self, message: dict) -> None:
        self.messages.append(message)


def _cards() -> list[CharacterCard]:
    return [
        CharacterCard(id=7, name="Mira", description="witch", personality="calm"),
        CharacterCard(id=8, name="Vera", description="genius", personality="lazy"),
    ]


def _room() -> SimpleNamespace:
    return SimpleNamespace(
        id=1, session_id="s1", scenario_prompt="", name="R", user_card_id=None,
    )


def _chat(rows: list[MessageRow], cards: list[CharacterCard]) -> SimpleNamespace:
    chat = SimpleNamespace()
    deleted: list[list[int]] = []
    chat.deleted = deleted
    chat.session_store = SimpleNamespace(
        get_session_messages=lambda cid, **kw: list(rows),
        delete_messages=lambda ids: deleted.append(list(ids)) or len(ids),
    )
    chat.card_repo = SimpleNamespace(
        get_character=lambda cid: next((c for c in cards if c.id == cid), None),
        get_user_card=lambda cid: None,
        get_default_user_card=lambda: None,
    )
    chat._short_cache = {"s1": []}
    return chat


def _engine(chat, cards: list[CharacterCard]) -> GroupEngine:
    rooms = SimpleNamespace(members=lambda room_id: [c.id for c in cards])
    return GroupEngine(chat, rooms)


def _patch_speak(monkeypatch, calls: list[dict]):
    async def fake_speak(self, ws, **kwargs):
        calls.append(kwargs)
        return "group_new", "new line"

    monkeypatch.setattr(GroupEngine, "speak", fake_speak)


def _rows() -> list[MessageRow]:
    return [
        MessageRow(id=1, session_id="s1", role="user", content="look"),
        MessageRow(id=2, session_id="s1", role="assistant", content="old line",
                   character_card_id=7),
    ]


def test_regenerate_reruns_the_original_speaker(monkeypatch) -> None:
    cards = _cards()
    chat = _chat(_rows(), cards)
    calls: list[dict] = []
    _patch_speak(monkeypatch, calls)
    ws = FakeWebSocket()

    result = asyncio.run(GroupEngine.regenerate(
        _engine(chat, cards), ws, room=_room(), message_row_id=2, user_card=None,
    ))

    assert result == ("group_new", "new line")
    assert calls[0]["character"].id == 7


def test_regenerate_rebuilds_the_trigger_from_prior_history(monkeypatch) -> None:
    cards = _cards()
    chat = _chat(_rows(), cards)
    calls: list[dict] = []
    _patch_speak(monkeypatch, calls)

    asyncio.run(GroupEngine.regenerate(
        _engine(chat, cards), FakeWebSocket(), room=_room(),
        message_row_id=2, user_card=None,
    ))

    assert calls[0]["user_input"] == "look"
    assert calls[0]["trigger_speaker"] == "user"
    assert calls[0]["history"] == []


def test_regenerate_deletes_the_old_row(monkeypatch) -> None:
    cards = _cards()
    chat = _chat(_rows(), cards)
    calls: list[dict] = []
    _patch_speak(monkeypatch, calls)

    asyncio.run(GroupEngine.regenerate(
        _engine(chat, cards), FakeWebSocket(), room=_room(),
        message_row_id=2, user_card=None,
    ))

    assert chat.deleted == [[2]]


def test_regenerate_does_not_run_an_election(monkeypatch) -> None:
    cards = _cards()
    chat = _chat(_rows(), cards)
    calls: list[dict] = []
    _patch_speak(monkeypatch, calls)
    ws = FakeWebSocket()

    called = {"elect": False}

    async def fake_elect(self, ws, **kwargs):
        called["elect"] = True
        return []

    monkeypatch.setattr(GroupEngine, "elect", fake_elect)

    asyncio.run(GroupEngine.regenerate(
        _engine(chat, cards), ws, room=_room(), message_row_id=2, user_card=None,
    ))

    assert called["elect"] is False
    assert not any(m["type"].startswith("group.elect") for m in ws.messages)
    assert not any(m["type"] == "group.chain.finished" for m in ws.messages)


def test_regenerate_unknown_row_returns_none() -> None:
    cards = _cards()
    chat = _chat(_rows(), cards)

    result = asyncio.run(GroupEngine.regenerate(
        _engine(chat, cards), FakeWebSocket(), room=_room(),
        message_row_id=999, user_card=None,
    ))

    assert result is None


def test_regenerate_rejects_user_messages() -> None:
    cards = _cards()
    chat = _chat(_rows(), cards)

    result = asyncio.run(GroupEngine.regenerate(
        _engine(chat, cards), FakeWebSocket(), room=_room(),
        message_row_id=1, user_card=None,
    ))

    assert result is None


def test_regenerate_rejects_rows_without_a_speaker() -> None:
    cards = _cards()
    rows = [MessageRow(id=5, session_id="s1", role="assistant", content="legacy")]
    chat = _chat(rows, cards)

    result = asyncio.run(GroupEngine.regenerate(
        _engine(chat, cards), FakeWebSocket(), room=_room(),
        message_row_id=5, user_card=None,
    ))

    assert result is None


def test_regenerate_rejects_deleted_character() -> None:
    cards = _cards()
    rows = [MessageRow(id=5, session_id="s1", role="assistant", content="gone",
                       character_card_id=99)]
    chat = _chat(rows, cards)

    result = asyncio.run(GroupEngine.regenerate(
        _engine(chat, cards), FakeWebSocket(), room=_room(),
        message_row_id=5, user_card=None,
    ))

    assert result is None


def test_speak_bounds_the_room_short_cache(monkeypatch) -> None:
    """Group turns rebuild history from the room, so the short cache is write
    only there — it must not grow without bound."""
    from src.server.group_engine import GROUP_SHORT_CACHE_LIMIT

    cards = _cards()
    chat = _chat(_rows(), cards)
    chat._cancelled = False
    chat._model_thinking_effort = lambda: "off"
    chat.client_and_model = lambda: (SimpleNamespace(base_url=""), "m", "p")
    chat._active_provider_family = lambda: "openai"
    chat._memory_block = lambda query, **kw: ""
    chat._model_limits = lambda: (128000, 100000)
    chat._short_cache = {"s1": []}

    def save_assistant(message_id, conv_id, content, character_id=None):
        chat._short_cache.setdefault(conv_id, []).append(
            {"role": "assistant", "content": content}
        )

    chat._save_assistant = save_assistant

    async def stream_one_reply(ws, **kwargs):
        return "line"

    chat._stream_one_reply = stream_one_reply
    chat._post_turn_emotion_pass = lambda conv_id, char_id=None: None

    async def maybe_queue_tts(ws, **kwargs):
        return None

    chat._maybe_queue_tts = maybe_queue_tts
    engine = _engine(chat, cards)

    async def run():
        for _ in range(GROUP_SHORT_CACHE_LIMIT * 3):
            await GroupEngine.speak(
                engine, FakeWebSocket(),
                room=_room(), character=cards[0], user_card=None,
                history=[], user_input="hi", should_stop=lambda: False,
            )

    asyncio.run(run())

    assert len(chat._short_cache["s1"]) <= GROUP_SHORT_CACHE_LIMIT

# SPDX-License-Identifier: MIT
"""Smoke test against a real ChatEngine.

Every other group test drives GroupEngine with SimpleNamespace fakes, so a typo
in an attribute name (say `_memory_blocks` instead of `_memory_block`) would
still pass the whole suite. This one wires the real ChatEngine over a temp
database and stubs only the LLM boundary."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from src.memory.cards import CharacterCard
from src.memory.rooms import RoomStore
from src.server.chat_engine import ChatEngine
from src.server.group_engine import GroupEngine
from src.server.risk_bridge import RiskBridge
from src.utils.fsar_config import FsarConfig


class FakeWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send_json(self, message: dict) -> None:
        self.messages.append(message)


@pytest.fixture()
def engine(tmp_path: Path, monkeypatch) -> ChatEngine:
    # Keep the Chroma store off the real FSAR home; the SQLite path comes from
    # the config property, which we point at the temp dir too.
    monkeypatch.setattr("src.memory.semantic.DATA_DIR", tmp_path)
    db_path = tmp_path / "memory.db"
    monkeypatch.setattr(
        FsarConfig, "memory_sqlite_path", property(lambda self: str(db_path)),
    )
    built = ChatEngine(FsarConfig(), RiskBridge())
    built._session_model_override = "stub:stub-model"
    return built


def _stub_stream(monkeypatch, text: str, seen: list[dict]) -> None:
    """Patch the LLM boundary through monkeypatch so it is always undone —
    assigning to the class directly would leak into every later test."""

    async def fake_stream(self, ws, **kwargs):
        seen.append(kwargs)
        await ws.send_json({
            "type": "chat.delta",
            "message_id": kwargs["message_id"],
            "conversation_id": kwargs["conv_id"],
            "content": text,
        })
        return text

    monkeypatch.setattr(ChatEngine, "_stream_one_reply", fake_stream)


def test_speak_runs_against_the_real_engine(engine: ChatEngine, monkeypatch) -> None:
    char_id = engine.card_repo.upsert_character(CharacterCard(
        id=None, name="Mira", description="A witch.", personality="Calm.",
    ))
    character = engine.card_repo.get_character(char_id)
    rooms = RoomStore(engine.config.memory_sqlite_path, engine.session_store)
    room = rooms.create(name="Room", character_ids=[char_id])

    seen: list[dict] = []
    _stub_stream(monkeypatch, "I am here.", seen)
    ws = FakeWebSocket()

    async def run():
        return await GroupEngine(engine, rooms).speak(
            ws,
            room=rooms.get(room.id),
            character=character,
            user_card=engine.card_repo.get_default_user_card(),
            history=[],
            user_input="hello",
            should_stop=lambda: False,
        )

    message_id, text = asyncio.run(run())

    assert text == "I am here."
    assert seen[0]["messages"][0]["role"] == "system"

    kinds = [m["type"] for m in ws.messages]
    assert kinds == [
        "group.speaker.start", "group.speaker.delta",
        "group.context", "group.speaker.done",
    ]

    # The real _track_context ran, so the gauge carries a real size.
    snapshot = next(m for m in ws.messages if m["type"] == "group.context")
    assert snapshot["used_tokens"] > 0
    assert snapshot["window_tokens"] > 0

    # The real engine persisted the turn, attributed to the speaker.
    rows = rooms.messages_with_speaker(room.id)
    assert len(rows) == 1
    assert rows[0].content == "I am here."
    assert rows[0].character_card_id == char_id

    # The row id must come back so the client can regenerate a fresh reply.
    done = ws.messages[-1]
    assert done["row_id"] == rows[0].id
    assert engine._msg_ids[message_id] == rows[0].id


def test_regenerate_rewrites_the_same_row_on_the_real_engine(
    engine: ChatEngine, monkeypatch
) -> None:
    char_id = engine.card_repo.upsert_character(CharacterCard(
        id=None, name="Kai", description="A sailor.", personality="Loud.",
    ))
    character = engine.card_repo.get_character(char_id)
    rooms = RoomStore(engine.config.memory_sqlite_path, engine.session_store)
    room = rooms.create(name="Room", character_ids=[char_id])
    original = engine.session_store.append_message(
        room.session_id, "assistant", "old words", character_card_id=char_id,
    )

    _stub_stream(monkeypatch, "new words", [])
    ws = FakeWebSocket()

    async def run():
        return await GroupEngine(engine, rooms).regenerate(
            ws,
            room=rooms.get(room.id),
            message_row_id=original,
            user_card=engine.card_repo.get_default_user_card(),
        )

    message_id, text = asyncio.run(run())

    assert text == "new words"
    assert message_id == str(original)

    # Same row, rewritten in place: no duplicate, no reordering.
    rows = rooms.messages_with_speaker(room.id)
    assert len(rows) == 1
    assert rows[0].id == original
    assert rows[0].content == "new words"

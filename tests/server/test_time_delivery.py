# SPDX-License-Identifier: MIT
"""The block must reach every prompt-building path, and disabling it must take
it back out again."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from src.memory.cards import CharacterCard
from src.server.chat_engine import ChatEngine
from src.server.risk_bridge import RiskBridge
from src.utils.fsar_config import FsarConfig


@pytest.fixture()
def engine(tmp_path: Path, monkeypatch) -> ChatEngine:
    monkeypatch.setattr("src.memory.semantic.DATA_DIR", tmp_path)
    db_path = tmp_path / "memory.db"
    monkeypatch.setattr(
        FsarConfig, "memory_sqlite_path", property(lambda self: str(db_path)),
    )
    built = ChatEngine(FsarConfig(), RiskBridge())
    monkeypatch.setattr(
        built, "_injection_slots",
        lambda *a, **k: {"memory": "", "strategy": "", "experience": ""},
    )
    # _build_prompt resolves the default character itself, and a temp database
    # has no cards in it.
    monkeypatch.setattr(built.card_repo, "get_default_character", _character)
    return built


def _character() -> CharacterCard:
    return CharacterCard(id=1, name="V", description="d", personality="p")


async def test_companion_prompt_carries_the_block(engine: ChatEngine):
    conv_id = engine.session_store.create().id
    prompt = await engine._build_prompt(conv_id, "companion", "hi")
    assert "<time>" in prompt and "</time>" in prompt


async def test_agent_prompt_carries_the_block(engine: ChatEngine):
    conv_id = engine.session_store.create().id
    prompt = await engine._build_prompt(conv_id, "agent", "hi")
    assert "<time>" in prompt


async def test_character_prompt_carries_the_block(engine: ChatEngine):
    conv_id = engine.session_store.create().id
    prompt = await engine._build_character_prompt(conv_id, "hi", _character())
    assert "<time>" in prompt


async def test_disabled_switch_removes_the_block(engine: ChatEngine):
    conv_id = engine.session_store.create().id
    engine.config.patch("time.enabled", False)
    assert "<time>" not in await engine._build_prompt(conv_id, "companion", "hi")
    assert "<time>" not in await engine._build_character_prompt(
        conv_id, "hi", _character()
    )


class _FakeWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send_json(self, message: dict) -> None:
        self.messages.append(message)


def _stub_stream(monkeypatch, seen: list[dict], text: str) -> None:
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


def _group_speak_prompt(engine: ChatEngine, monkeypatch, name: str) -> str:
    from src.memory.rooms import RoomStore
    from src.server.group_engine import GroupEngine

    char_id = engine.card_repo.upsert_character(CharacterCard(
        id=None, name=name, description="Someone.", personality="Plain.",
    ))
    character = engine.card_repo.get_character(char_id)
    rooms = RoomStore(engine.config.memory_sqlite_path, engine.session_store)
    room = rooms.create(name="Room", character_ids=[char_id])

    seen: list[dict] = []
    _stub_stream(monkeypatch, seen, "I am here.")

    async def run():
        return await GroupEngine(engine, rooms).speak(
            _FakeWebSocket(),
            room=rooms.get(room.id),
            character=character,
            user_card=engine.card_repo.get_default_user_card(),
            history=[],
            user_input="hello",
            should_stop=lambda: False,
        )

    asyncio.run(run())
    return seen[0]["messages"][0]["content"]


def test_group_speak_carries_the_block_and_the_dedupe_line(
    engine: ChatEngine, monkeypatch
):
    """The group path builds its own prompt, so it needs its own assertion —
    and its block must carry the dedupe line."""
    system = _group_speak_prompt(engine, monkeypatch, "Mira")
    assert "<time>" in system
    assert "already greeted them back" in system


def test_group_speak_omits_the_block_when_disabled(
    engine: ChatEngine, monkeypatch
):
    engine.config.patch("time.enabled", False)
    system = _group_speak_prompt(engine, monkeypatch, "Kai")
    assert "<time>" not in system

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


def test_injection_slots_asks_for_the_older_history(monkeypatch):
    """The dated-history source needs the session and the size of the live
    window, so the engine has to pass both down."""
    built = ChatEngine(FsarConfig(), RiskBridge())
    conv_id = built.session_store.create().id
    built.session_store.append_message(conv_id, "user", "hello")
    built._ensure_short(conv_id)

    from src.memory.recall import RecallResult

    seen: dict = {}

    def fake_recall(query, **kwargs):
        seen.update(kwargs)
        return RecallResult()

    monkeypatch.setattr(built.recall, "recall_for_context", fake_recall)
    monkeypatch.setattr(
        built.injection_pipeline, "build_slots",
        lambda *a, **k: {"memory": "", "strategy": "", "experience": ""},
    )
    built._injection_slots("hi", conv_id=conv_id)

    assert seen["history_session"] == conv_id
    assert seen["history_skip"] == len(built._short_cache[conv_id])


@pytest.fixture()
def memory_engine(tmp_path: Path, monkeypatch) -> ChatEngine:
    """A real engine over a real recall path with an offline judge, so the
    dated-history source can be asserted end to end without a model call."""
    monkeypatch.setattr("src.memory.semantic.DATA_DIR", tmp_path)
    db_path = tmp_path / "memory.db"
    monkeypatch.setattr(
        FsarConfig, "memory_sqlite_path", property(lambda self: str(db_path)),
    )
    built = ChatEngine(FsarConfig(), RiskBridge())
    from src.memory.judge import NullJudge
    from src.memory.pipeline import InjectionPipeline

    built.injection_pipeline = InjectionPipeline(
        judge=NullJudge(),
        budget_chars=built.config.inject_budget_chars,
        candidate_cap=built.config.inject_candidate_cap,
        score_floor=built.config.inject_score_floor,
        max_item_chars=built.config.inject_max_item_chars,
    )
    return built


def test_older_history_lands_in_the_memory_block(memory_engine: ChatEngine):
    """The dated memories come out of SQLite, so this holds with the embedder
    unreachable — which is the whole point of the split."""
    engine = memory_engine
    conv_id = engine.session_store.create().id
    for i in range(14):
        engine.session_store.append_message(conv_id, "user", f"note number {i}")
    engine._ensure_short(conv_id)

    block = engine._memory_block("hi", conv_id=conv_id)

    assert "(1 minute ago) note number 3" in block
    assert "note number 13" not in block

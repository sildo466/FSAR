# SPDX-License-Identifier: MIT
"""The arrival gap is derived from message timestamps and held in memory for
the duration of one arrival."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

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
    return ChatEngine(FsarConfig(), RiskBridge())


def _backdate(engine: ChatEngine, row_id: int, **delta) -> None:
    stamp = (datetime.now() - timedelta(**delta)).isoformat()
    with engine.session_store._connect() as conn:
        conn.execute(
            "UPDATE conversations SET timestamp = ? WHERE id = ?", (stamp, row_id),
        )
        conn.commit()


def test_first_ever_message_has_no_gap(engine: ChatEngine):
    conv_id = engine.session_store.create().id
    engine.note_arrival(conv_id)
    assert engine.arrival_gap(conv_id) is None


def test_gap_is_measured_from_the_previous_message(engine: ChatEngine):
    conv_id = engine.session_store.create().id
    row_id = engine.session_store.append_message(conv_id, "user", "hello")
    assert row_id is not None
    _backdate(engine, row_id, days=3)

    engine.note_arrival(conv_id)
    gap = engine.arrival_gap(conv_id)
    assert gap is not None
    assert 3 * 86400 - 60 < gap < 3 * 86400 + 60


def test_save_user_records_the_arrival(engine: ChatEngine):
    conv_id = engine.session_store.create().id
    row_id = engine.session_store.append_message(conv_id, "user", "hello")
    _backdate(engine, row_id, hours=2)

    engine._save_user(conv_id, "back again")
    gap = engine.arrival_gap(conv_id)
    assert gap is not None
    assert 2 * 3600 - 60 < gap < 2 * 3600 + 60


def test_unknown_conversation_reports_none(engine: ChatEngine):
    assert engine.arrival_gap("never-seen") is None


def test_time_block_reads_config_and_gap(engine: ChatEngine):
    conv_id = engine.session_store.create().id
    engine._arrivals[conv_id] = 3 * 86400
    engine.config.patch("user.birthday", "09-29")
    block = engine._time_block(conv_id)
    assert "The user's last message was 3 days ago" in block
    assert "The user's birthday is 09-29" in block


def test_time_block_honours_the_disable_switch(engine: ChatEngine):
    conv_id = engine.session_store.create().id
    engine.config.patch("time.enabled", False)
    assert engine._time_block(conv_id) == ""


def test_time_block_ignores_a_gap_below_the_floor(engine: ChatEngine):
    conv_id = engine.session_store.create().id
    engine.config.patch("time.gap_floor_minutes", 600)
    engine._arrivals[conv_id] = 60 * 60
    assert "last message" not in engine._time_block(conv_id)


def test_time_block_survives_a_bad_floor_value(engine: ChatEngine):
    conv_id = engine.session_store.create().id
    engine.config.patch("time.gap_floor_minutes", "not-a-number")
    assert "<time>" in engine._time_block(conv_id)


def test_time_block_drops_a_junk_birthday(engine: ChatEngine):
    conv_id = engine.session_store.create().id
    engine.config.patch("user.birthday", "02-30")
    assert "birthday" not in engine._time_block(conv_id)

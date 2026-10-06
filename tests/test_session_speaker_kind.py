# SPDX-License-Identifier: MIT
"""A room message may name a speaker that is not a character card."""

from __future__ import annotations

import tempfile
from pathlib import Path

from src.memory.session_store import SessionStore


def _store() -> SessionStore:
    tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    return SessionStore(Path(tmp.name) / "test.db")


def test_legacy_character_row_keeps_working() -> None:
    store = _store()
    conv = store.create(kind="group").id
    row_id = store.append_message(conv, "assistant", "hi", character_card_id=7)
    rows = store.get_session_messages(conv)
    row = next(r for r in rows if r.id == row_id)
    assert row.character_card_id == 7
    assert row.speaker_kind is None
    assert row.speaker_ref is None


def test_agent_row_round_trips() -> None:
    store = _store()
    conv = store.create(kind="group").id
    row_id = store.append_message(
        conv, "assistant", "on it",
        speaker_kind="agent", speaker_ref="claude@laptop",
    )
    row = next(r for r in store.get_session_messages(conv) if r.id == row_id)
    assert row.speaker_kind == "agent"
    assert row.speaker_ref == "claude@laptop"
    assert row.character_card_id is None


def test_recent_messages_carry_the_new_columns_too() -> None:
    store = _store()
    conv = store.create(kind="group").id
    store.append_message(
        conv, "assistant", "on it",
        speaker_kind="agent", speaker_ref="claude@laptop",
    )
    rows = store.get_recent_messages(conv, limit=5)
    assert rows[-1].speaker_kind == "agent"
    assert rows[-1].speaker_ref == "claude@laptop"


def test_migration_is_idempotent() -> None:
    tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    db = Path(tmp.name) / "test.db"
    SessionStore(db)
    second = SessionStore(db)  # runs the migration again
    conv = second.create(kind="group").id
    assert second.append_message(conv, "user", "x") is not None

# SPDX-License-Identifier: MIT
from __future__ import annotations

import tempfile
from pathlib import Path

from src.memory.session_store import SessionStore


def _store() -> tuple[SessionStore, str]:
    tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    store = SessionStore(Path(tmp.name) / "test.db")
    session = store.create()
    return store, session.id


def test_append_message_persists_speaker() -> None:
    store, cid = _store()
    store.append_message(cid, "assistant", "hello", character_card_id=42)
    rows = store.get_session_messages(cid)
    assert len(rows) == 1
    assert rows[0].character_card_id == 42
    assert rows[0].to_dict()["character_id"] == 42


def test_append_message_defaults_speaker_to_none() -> None:
    store, cid = _store()
    store.append_message(cid, "user", "hi")
    rows = store.get_session_messages(cid)
    assert rows[0].character_card_id is None
    # The key is omitted (not None) so legacy consumers can setdefault it.
    assert "character_id" not in rows[0].to_dict()


def test_recent_messages_carry_speaker() -> None:
    store, cid = _store()
    store.append_message(cid, "assistant", "a", character_card_id=7)
    store.append_message(cid, "user", "b")
    recent = store.get_recent_messages(cid)
    assert [r.character_card_id for r in recent] == [7, None]


def test_migration_is_idempotent_and_keeps_attribution() -> None:
    store, cid = _store()
    store.append_message(cid, "assistant", "x", character_card_id=7)
    store._init_db()
    store._init_db()
    assert store.get_session_messages(cid)[0].character_card_id == 7


def test_summary_and_tags_survive_column_reorder() -> None:
    store, cid = _store()
    store.append_message(cid, "assistant", "body", summary="sum", tags="reply")
    row = store.get_session_messages(cid)[0]
    assert row.summary == "sum"
    assert row.tags == "reply"
    assert row.content == "body"


def test_legacy_rows_still_accept_session_character_enrichment() -> None:
    """conversation.history fills the speaker for rows that predate attribution
    via setdefault, so an unattributed row must not carry the key at all."""
    store, cid = _store()
    store.set_character(cid, 5)
    store.append_message(cid, "assistant", "old reply")
    payload = store.get_session_messages(cid)[0].to_dict()
    payload.setdefault("character_id", 5)
    payload.setdefault("character_name", "Mira")
    assert payload["character_id"] == 5
    assert payload["character_name"] == "Mira"

# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import sys
import sqlite3
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.memory.session_store import SessionStore


def test_migrate_adds_character_card_id_column():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = Path(tmp) / "test.db"
        store = SessionStore(db)
        store._init_db()
        with sqlite3.connect(db) as conn:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(sessions)").fetchall()]
        assert "character_card_id" in cols


def test_migrate_is_idempotent():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = Path(tmp) / "test.db"
        store = SessionStore(db)
        store._init_db()
        store._init_db()
        store._init_db()


def test_set_and_get_character():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = Path(tmp) / "test.db"
        store = SessionStore(db)
        s = store.create()
        store.set_character(s.id, 42)
        assert store.get_character(s.id) == 42


def test_get_character_default_none():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = Path(tmp) / "test.db"
        store = SessionStore(db)
        s = store.create()
        assert store.get_character(s.id) is None

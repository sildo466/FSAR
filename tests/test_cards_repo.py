# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.memory.cards import CardRepo


def test_ensure_tables_creates_all_three_tables():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = Path(tmp) / "test.db"
        repo = CardRepo(db)
        with sqlite3.connect(db) as conn:
            repo.ensure_tables(conn)
            names = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        assert "character_cards" in names
        assert "user_cards" in names
        assert "emotion_audit" in names
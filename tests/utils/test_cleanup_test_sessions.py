# SPDX-License-Identifier: MIT
from __future__ import annotations

from pathlib import Path

from src.memory.session_store import SessionStore
from src.utils.cleanup_sessions import cleanup, find_sessions_by_title


def _seed(path: Path) -> SessionStore:
    store = SessionStore(path)
    keep = store.create()
    store.rename(keep.id, "real conversation")
    store.append_message(keep.id, "user", "hello")
    for _ in range(3):
        row = store.create()
        store.rename(row.id, "delete it")
    blank = store.create()
    store.rename(blank.id, "")
    return store


def test_find_matches_exact_title_case_insensitively(tmp_path: Path):
    store = _seed(tmp_path / "m.db")
    store.create()
    found = find_sessions_by_title(store, "delete it")
    assert len(found) == 3


def test_find_does_not_match_substring(tmp_path: Path):
    store = SessionStore(tmp_path / "m.db")
    row = store.create()
    store.rename(row.id, "please delete it now")
    assert find_sessions_by_title(store, "delete it") == []


def test_cleanup_apply_false_changes_nothing(tmp_path: Path):
    db = tmp_path / "m.db"
    _seed(db)
    deleted, backup = cleanup(db, "delete it", apply=False)
    assert deleted == 3
    assert backup is None
    assert len(find_sessions_by_title(SessionStore(db), "delete it")) == 3


def test_cleanup_apply_true_deletes_and_backs_up(tmp_path: Path):
    db = tmp_path / "m.db"
    _seed(db)
    deleted, backup = cleanup(db, "delete it", apply=True)
    assert deleted == 3
    assert backup is not None and backup.is_file()
    assert find_sessions_by_title(SessionStore(db), "delete it") == []
    assert len(SessionStore(db).list(limit=100, kind=None)) == 2


def test_cleanup_removes_attached_messages(tmp_path: Path):
    db = tmp_path / "m.db"
    store = SessionStore(db)
    row = store.create()
    store.rename(row.id, "delete it")
    store.append_message(row.id, "user", "hi")
    store.append_message(row.id, "assistant", "yo")
    cleanup(db, "delete it", apply=True)
    import sqlite3

    with sqlite3.connect(db) as conn:
        left = conn.execute(
            "SELECT COUNT(*) FROM conversations WHERE session_fk = ?", (row.id,)
        ).fetchone()[0]
    assert left == 0

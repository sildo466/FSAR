# SPDX-License-Identifier: MIT
from __future__ import annotations

import sqlite3
from pathlib import Path

from src.notifications.store import NOTIFICATIONS_TABLE, NotificationStore
from src.security.content_guard import ContentGuard
from src.security.content_screen import ScreenVerdict


class _FakeConfig:
    def get(self, path, default=None):
        return default

    def get_judge(self):
        return {}

    def get_active_provider(self):
        return {}


def test_add_and_list_roundtrip(tmp_path: Path):
    store = NotificationStore(tmp_path / "m.db")
    row_id = store.add(kind="release", title="FSAR v0.7.0", ref="v0.7.0",
                       body="notes", url="https://example.test/r",
                       payload={"tag": "v0.7.0", "channel": "stable"})
    assert isinstance(row_id, int)
    rows = store.list()
    assert len(rows) == 1
    assert rows[0]["kind"] == "release"
    assert rows[0]["ref"] == "v0.7.0"
    assert rows[0]["body"] == "notes"
    assert rows[0]["url"] == "https://example.test/r"
    assert rows[0]["payload"] == {"tag": "v0.7.0", "channel": "stable"}
    assert rows[0]["read"] == 0


def test_add_is_idempotent_on_kind_and_ref(tmp_path: Path):
    store = NotificationStore(tmp_path / "m.db")
    assert store.add(kind="release", title="a", ref="v0.7.0") is not None
    assert store.add(kind="release", title="a again", ref="v0.7.0") is None
    assert len(store.list()) == 1


def test_add_allows_repeated_ref_across_kinds(tmp_path: Path):
    store = NotificationStore(tmp_path / "m.db")
    store.add(kind="release", title="a", ref="v0.7.0")
    store.add(kind="announcement", title="b", ref="v0.7.0")
    assert len(store.list()) == 2


def test_add_without_ref_does_not_dedupe(tmp_path: Path):
    store = NotificationStore(tmp_path / "m.db")
    store.add(kind="review", title="a")
    store.add(kind="review", title="b")
    assert len(store.list()) == 2


def test_filter_by_kind(tmp_path: Path):
    store = NotificationStore(tmp_path / "m.db")
    store.add(kind="review", title="r", ref="1")
    store.add(kind="release", title="v", ref="v0.7.0")
    only = store.list(kind="review")
    assert [row["title"] for row in only] == ["r"]


def test_unread_count_and_mark_read(tmp_path: Path):
    store = NotificationStore(tmp_path / "m.db")
    first = store.add(kind="review", title="r", ref="1")
    store.add(kind="review", title="r2", ref="2")
    assert store.unread_count() == 2
    assert store.mark_read([first]) == 1
    assert store.unread_count() == 1
    assert store.mark_read() == 1
    assert store.unread_count() == 0


def test_unread_only_filter(tmp_path: Path):
    store = NotificationStore(tmp_path / "m.db")
    first = store.add(kind="review", title="r", ref="1")
    store.add(kind="review", title="r2", ref="2")
    store.mark_read([first])
    assert [row["title"] for row in store.list(unread_only=True)] == ["r2"]


def test_clear_deletes_notifications_only(tmp_path: Path):
    db = tmp_path / "m.db"
    guard = ContentGuard(_FakeConfig(), db_path=db, autostart=False)
    qid = guard.record("chunk", "1", "suspicious", kind="memory_chunk",
                       verdict=ScreenVerdict(False, 0.9))
    store = NotificationStore(db)
    store.add(kind="review", title="r", ref=str(qid))
    store.add(kind="release", title="v", ref="v0.7.0")

    assert store.clear() == 2
    assert store.list() == []
    with sqlite3.connect(db) as conn:
        left = conn.execute("SELECT COUNT(*) FROM content_quarantine").fetchone()[0]
    assert left == 1


def test_survives_reopen_and_is_idempotent_on_migration(tmp_path: Path):
    db = tmp_path / "m.db"
    NotificationStore(db).add(kind="review", title="r", ref="1")
    again = NotificationStore(db)
    assert len(again.list()) == 1
    with sqlite3.connect(db) as conn:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    assert NOTIFICATIONS_TABLE in names


def test_newest_first(tmp_path: Path):
    store = NotificationStore(tmp_path / "m.db")
    store.add(kind="review", title="older", ref="1", created_at="2026-01-01T00:00:00")
    store.add(kind="review", title="newer", ref="2", created_at="2026-02-01T00:00:00")
    assert [row["title"] for row in store.list()] == ["newer", "older"]

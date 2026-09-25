# SPDX-License-Identifier: MIT
from __future__ import annotations

import pytest

from src.security.content_guard import ContentGuard
from src.security.content_screen import ScreenVerdict


class _FakeConfig:
    def __init__(self, enabled=True, threshold=0.5):
        self._enabled = enabled
        self._threshold = threshold

    def get(self, path, default=None):
        if path == "security.content_screening.enabled":
            return self._enabled
        if path == "security.content_screening.threshold":
            return self._threshold
        return default

    def get_judge(self):
        return {}

    def get_active_provider(self):
        return {}


@pytest.fixture
def guard(tmp_path):
    return ContentGuard(_FakeConfig(), db_path=tmp_path / "memory.db", autostart=False)


def test_defaults_enabled_when_config_silent(tmp_path):
    class _Silent:
        def get(self, path, default=None):
            return default

        def get_judge(self):
            return {}

        def get_active_provider(self):
            return {}

    g = ContentGuard(_Silent(), db_path=tmp_path / "memory.db", autostart=False)
    assert g.enabled is True
    assert g.threshold == pytest.approx(0.5)


def test_digest_is_stable_and_content_addressed(guard):
    assert guard.digest("abc") == guard.digest("abc")
    assert guard.digest("abc") != guard.digest("abd")


def test_whitelist_roundtrip(guard):
    assert guard.is_whitelisted("hello") is False
    guard.add_to_whitelist("hello", added_by="restore")
    assert guard.is_whitelisted("hello") is True
    assert guard.remove_from_whitelist("hello") is True
    assert guard.is_whitelisted("hello") is False
    assert guard.remove_from_whitelist("hello") is False


def test_whitelist_is_idempotent(guard):
    guard.add_to_whitelist("hello", added_by="restore")
    guard.add_to_whitelist("hello", added_by="manual", note="second")
    assert len(guard.list_whitelist()) == 1


def test_record_and_list(guard):
    qid = guard.record(
        "chunk", "7", "bad payload",
        kind="memory_chunk",
        verdict=ScreenVerdict(False, 0.91),
    )
    rows = guard.list_quarantine()
    assert len(rows) == 1
    assert rows[0]["id"] == qid
    assert rows[0]["store"] == "chunk"
    assert rows[0]["record_ref"] == "7"
    assert rows[0]["text"] == "bad payload"
    assert rows[0]["verdict_confidence"] == pytest.approx(0.91)
    assert rows[0]["screened_by"] == "llm"
    assert rows[0]["state"] == "quarantined"
    assert rows[0]["sha256"] == guard.digest("bad payload")


def test_record_keeps_original_fields_as_json(guard):
    guard.record(
        "card", "3", "card text",
        kind="character_card",
        verdict=ScreenVerdict(False, 0.8),
        original_fields={"description": "d", "personality": "p"},
    )
    row = guard.list_quarantine()[0]
    assert row["original_fields"] == {"description": "d", "personality": "p"}


def test_screened_by_reflects_route(guard):
    guard.screener._jev = object()
    guard.record("chunk", "1", "x", kind="memory_chunk", verdict=ScreenVerdict(False, 0.9))
    assert guard.list_quarantine()[0]["screened_by"] == "jev"


def test_purge_hides_row_and_marks_state(guard):
    qid = guard.record("chunk", "1", "x", kind="memory_chunk", verdict=ScreenVerdict(False, 0.9))
    assert guard.purge(qid) is True
    assert guard.list_quarantine() == []
    assert guard.get_quarantine(qid)["state"] == "purged"
    assert guard.purge(qid) is False


def test_mark_restored_hides_row(guard):
    qid = guard.record("chunk", "1", "x", kind="memory_chunk", verdict=ScreenVerdict(False, 0.9))
    assert guard.mark_restored(qid) is True
    assert guard.list_quarantine() == []
    assert guard.get_quarantine(qid)["state"] == "restored"


def test_include_resolved_shows_all(guard):
    a = guard.record("chunk", "1", "x", kind="memory_chunk", verdict=ScreenVerdict(False, 0.9))
    guard.record("chunk", "2", "y", kind="memory_chunk", verdict=ScreenVerdict(False, 0.9))
    guard.purge(a)
    assert len(guard.list_quarantine()) == 1
    assert len(guard.list_quarantine(include_resolved=True)) == 2


def test_report_roundtrip(guard):
    assert guard.get_report() == {}
    guard.set_report({"unavailable": 3, "reason": "no provider"})
    assert guard.get_report()["unavailable"] == 3


def test_tables_are_created_on_a_fresh_db(guard):
    import sqlite3

    with sqlite3.connect(guard.db_path) as conn:
        names = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert {"content_quarantine", "content_whitelist"} <= names

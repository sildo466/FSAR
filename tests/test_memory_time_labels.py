# SPDX-License-Identifier: MIT
"""The dated-history dimension reads the SQLite conversation log, so it works
whether or not the vector store is reachable."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from src.memory.candidates import candidates_from_recall
from src.memory.long_term import LongTermMemory
from src.memory.recall import MemoryRecall, RecallResult


def _iso(days: int) -> str:
    return (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")


def test_older_history_carries_its_age():
    result = RecallResult(
        older_history=[{
            "text": "the user mentioned an interview",
            "timestamp": _iso(5),
            "role": "user",
        }],
        memory_chunks=[{
            "title": "Deploy",
            "body": "steps",
            "source": "runbook",
            "created_at": _iso(12),
        }],
    )
    by_key = {c.key: c.text for c in candidates_from_recall(result)}
    assert by_key["D1"] == "- (5 days ago) the user mentioned an interview"
    assert by_key["F1"] == "- (12 days ago) Deploy: steps"


def test_vector_hits_are_left_undated():
    """The embedding-backed recall keeps behaving exactly as it did before the
    time feature existed."""
    result = RecallResult(
        similar_conversations=[{
            "text": "semantic hit",
            "metadata": {"ts": str(int(datetime.now().timestamp()))},
            "distance": 0.1,
        }],
    )
    by_key = {c.key: c.text for c in candidates_from_recall(result)}
    assert by_key["H1"] == "- semantic hit"


def test_missing_timestamps_leave_the_text_alone():
    result = RecallResult(
        older_history=[{"text": "no timestamp", "role": "user"}],
        memory_chunks=[{"title": "T", "body": "b", "source": "s"}],
    )
    by_key = {c.key: c.text for c in candidates_from_recall(result)}
    assert by_key["D1"] == "- no timestamp"
    assert by_key["F1"] == "- T: b"


def test_unparseable_timestamps_leave_the_text_alone():
    result = RecallResult(
        older_history=[{"text": "bad ts", "timestamp": "nonsense", "role": "user"}],
        memory_chunks=[{
            "title": "T", "body": "b", "source": "s", "created_at": "nonsense",
        }],
    )
    by_key = {c.key: c.text for c in candidates_from_recall(result)}
    assert by_key["D1"] == "- bad ts"
    assert by_key["F1"] == "- T: b"


def _recall(tmp_path: Path, rows: int) -> MemoryRecall:
    store = LongTermMemory(tmp_path / "memory.db")
    conv = "c1"
    for i in range(rows):
        store.save_message(conv, "user", f"message {i}")
    return MemoryRecall(long_term=store)


def test_older_history_skips_the_live_window(tmp_path: Path):
    recall = _recall(tmp_path, 8)
    result = recall.recall_for_context("q", history_session="c1",
                                       history_skip=3, history_limit=2)
    assert [h["text"] for h in result.older_history] == ["message 3", "message 4"]


def test_older_history_is_empty_without_a_session(tmp_path: Path):
    recall = _recall(tmp_path, 5)
    result = recall.recall_for_context("q", history_limit=3)
    assert result.older_history == []


def test_older_history_returns_everything_when_the_window_is_empty(tmp_path: Path):
    recall = _recall(tmp_path, 3)
    result = recall.recall_for_context("q", history_session="c1", history_limit=5)
    assert [h["text"] for h in result.older_history] == [
        "message 0", "message 1", "message 2",
    ]


def test_older_history_is_empty_when_asked_for_nothing(tmp_path: Path):
    recall = _recall(tmp_path, 5)
    result = recall.recall_for_context("q", history_session="c1", history_limit=0)
    assert result.older_history == []

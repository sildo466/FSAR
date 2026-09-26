# SPDX-License-Identifier: MIT
from __future__ import annotations

from datetime import datetime, timedelta

from src.memory.candidates import candidates_from_recall
from src.memory.recall import RecallResult


def _iso(days: int) -> str:
    return (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")


def _epoch(days: int) -> str:
    return str(int((datetime.now() - timedelta(days=days)).timestamp()))


def test_history_and_facts_carry_their_age():
    result = RecallResult(
        similar_conversations=[{
            "text": "the user mentioned an interview",
            "metadata": {"ts": _epoch(5)},
            "distance": 0.1,
        }],
        memory_chunks=[{
            "title": "Deploy",
            "body": "steps",
            "source": "runbook",
            "created_at": _iso(12),
        }],
    )
    by_source = {c.source: c.text for c in candidates_from_recall(result)}
    assert by_source["history"] == "- (5 days ago) the user mentioned an interview"
    assert by_source["fact"] == "- (12 days ago) Deploy: steps"


def test_missing_timestamps_leave_the_text_alone():
    result = RecallResult(
        similar_conversations=[
            {"text": "no timestamp", "metadata": {}, "distance": 0.0},
        ],
        memory_chunks=[{"title": "T", "body": "b", "source": "s"}],
    )
    by_source = {c.source: c.text for c in candidates_from_recall(result)}
    assert by_source["history"] == "- no timestamp"
    assert by_source["fact"] == "- T: b"


def test_unparseable_timestamps_leave_the_text_alone():
    result = RecallResult(
        similar_conversations=[{
            "text": "bad ts", "metadata": {"ts": "nonsense"}, "distance": 0.0,
        }],
        memory_chunks=[{
            "title": "T", "body": "b", "source": "s", "created_at": "nonsense",
        }],
    )
    by_source = {c.source: c.text for c in candidates_from_recall(result)}
    assert by_source["history"] == "- bad ts"
    assert by_source["fact"] == "- T: b"

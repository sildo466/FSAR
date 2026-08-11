# SPDX-License-Identifier: MIT
from __future__ import annotations

from src.memory.recall import MemoryRecall


class _FakeUserModel:
    def get_profile(self):
        return {}

    def get_all_preferences(self):
        return {}

    def get_top_patterns(self, limit=10):
        return []


class _FakeExperience:
    def search_chunks(self, keyword, limit=10):
        return []


class _FakeSemantic:
    def __init__(self):
        self.calls: list[dict] = []

    def search(self, query, n=5, where=None):
        self.calls.append({"query": query, "n": n, "where": where})
        return []


def _recall(semantic):
    return MemoryRecall(
        long_term=object(),
        semantic=semantic,
        user_model=_FakeUserModel(),
        feedback=object(),
        experience_store=_FakeExperience(),
    )


def test_recall_scopes_semantic_by_session_ids():
    semantic = _FakeSemantic()
    recall = _recall(semantic)
    recall.recall_for_context("hello", session_ids={"b", "a"})
    assert semantic.calls
    assert semantic.calls[-1]["where"] == {"session_id": {"$in": ["a", "b"]}}


def test_recall_stays_global_when_no_session_ids():
    semantic = _FakeSemantic()
    recall = _recall(semantic)
    recall.recall_for_context("hello")
    assert semantic.calls
    assert semantic.calls[-1]["where"] is None


def test_recall_skips_semantic_when_character_has_no_sessions():
    semantic = _FakeSemantic()
    recall = _recall(semantic)
    result = recall.recall_for_context("hello", session_ids=set())
    assert semantic.calls == []
    assert result.is_empty

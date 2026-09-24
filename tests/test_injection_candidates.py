# SPDX-License-Identifier: MIT
from __future__ import annotations

from src.memory.candidates import (
    Candidate,
    candidates_from_experience,
    candidates_from_recall,
    candidates_from_strategy,
    cap_by_source,
)
from src.memory.recall import RecallResult


def test_recall_result_becomes_candidates_with_source_and_priority():
    result = RecallResult(
        profile={"城市": "杭州"},
        preferences={"tone": "简短"},
        patterns=[{"pattern": "深夜提问", "count": 23}],
        memory_chunks=[{"title": "部署", "body": "挂载到 /data", "source": "x"}],
        similar_conversations=[{"text": "上次改过挂载路径", "metadata": {}, "distance": 0.2}],
    )
    cands = {c.source: c for c in candidates_from_recall(result)}

    assert set(cands) == {"profile", "preference", "pattern", "fact", "history"}
    assert cands["fact"].priority == 0
    assert cands["profile"].priority == 1
    assert cands["history"].priority == 4
    assert cands["profile"].text == "- 城市: 杭州"
    assert cands["fact"].text == "- 部署: 挂载到 /data"
    assert cands["pattern"].text == "- 深夜提问 (x23)"
    assert cands["history"].text == "- 上次改过挂载路径"


def test_history_text_is_not_truncated_at_200_chars():
    long_text = "记" * 400
    result = RecallResult(similar_conversations=[{"text": long_text}])
    cands = [c for c in candidates_from_recall(result) if c.source == "history"]
    assert len(cands) == 1
    assert len(cands[0].text) == 400 + len("- ")


def test_candidate_chars_matches_text_length():
    c = Candidate(source="profile", key="P1", text="- 城市: 杭州", priority=1)
    assert c.chars == len(c.text)


def test_empty_result_yields_no_candidates():
    assert candidates_from_recall(RecallResult()) == []


def _cand(source, key):
    from src.memory.candidates import PRIORITY
    return Candidate(source, key, f"- {source} {key}", PRIORITY[source])


def test_cap_is_round_robin_so_low_priority_sources_survive():
    cands = [_cand("profile", f"U{i}") for i in range(10)]
    cands += [_cand("history", f"H{i}") for i in range(3)]

    kept = cap_by_source(cands, cap=6)

    assert len(kept) == 6
    assert {"H0", "H1", "H2"} <= {c.key for c in kept}


def test_cap_returns_everything_when_under_limit():
    cands = [_cand("profile", "U1"), _cand("history", "H1")]
    assert len(cap_by_source(cands, cap=40)) == 2


def test_cap_drains_remaining_slots_when_a_source_runs_out():
    cands = [_cand("history", f"H{i}") for i in range(8)]
    kept = cap_by_source(cands, cap=5)
    assert len(kept) == 5


class _Exp:
    def __init__(self, name, category, description):
        self.name = name
        self.category = category
        self.description = description


class _FakeExpStore:
    def __init__(self, items):
        self._items = items

    def list_for_index(self):
        return self._items


class _FakeStrategy:
    def __init__(self, lines):
        self._lines = lines

    def item_lines(self):
        return self._lines


def test_experience_index_becomes_candidates():
    store = _FakeExpStore([
        _Exp("群聊", "group", "per-scene cast 配置"),
        _Exp("桌宠", "pet", "手撸简易 Spine"),
    ])
    cands = candidates_from_experience(store, max_desc_chars=60)
    assert [c.source for c in cands] == ["experience", "experience"]
    assert cands[0].key == "E1"
    assert cands[0].priority == 3
    assert "群聊" in cands[0].text


def test_experience_description_is_capped():
    store = _FakeExpStore([_Exp("x", "c", "y" * 500)])
    cands = candidates_from_experience(store, max_desc_chars=60)
    assert "y" * 60 in cands[0].text
    assert "y" * 61 not in cands[0].text


def test_experience_without_description_renders_name_only():
    store = _FakeExpStore([_Exp("裸名", "c", "")])
    cands = candidates_from_experience(store, max_desc_chars=60)
    assert cands[0].text == "- 裸名"


def test_strategy_items_become_candidates():
    cands = candidates_from_strategy(_FakeStrategy(["- 先跑最小复现", "- 大改动先开临时分支"]))
    assert [c.source for c in cands] == ["strategy", "strategy"]
    assert cands[0].priority == 2
    assert cands[1].key == "S2"

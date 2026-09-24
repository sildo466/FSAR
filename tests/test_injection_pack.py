# SPDX-License-Identifier: MIT
from __future__ import annotations

from src.memory.candidates import Candidate
from src.memory.pack import pack


def c(key, text, priority=1, source="profile"):
    return Candidate(source, key, text, priority)


def test_items_are_atomic_never_cut_mid_item():
    a = c("a", "x" * 10)
    b = c("b", "y" * 10)
    kept = pack([a, b], {}, budget_chars=15, score_floor=0.0, max_item_chars=600)
    assert [k.key for k in kept] == ["a"]


def test_budget_is_respected_exactly():
    cands = [c(f"k{i}", "z" * 10) for i in range(5)]
    kept = pack(cands, {}, budget_chars=32, score_floor=0.0, max_item_chars=600)
    assert sum(k.chars for k in kept) <= 32
    assert len(kept) == 3


def test_scores_reorder_ahead_of_priority():
    low_pri_high_score = c("H1", "history item", priority=4, source="history")
    high_pri_low_score = c("U1", "profile item", priority=1)
    kept = pack(
        [high_pri_low_score, low_pri_high_score],
        {"H1": 0.9, "U1": 0.2},
        budget_chars=20, score_floor=0.0, max_item_chars=600,
    )
    assert [k.key for k in kept] == ["H1"]


def test_score_floor_drops_items_and_can_leave_budget_unused():
    cands = [c("a", "aaa"), c("b", "bbb"), c("d", "ddd")]
    kept = pack(cands, {"a": 0.9, "b": 0.1, "d": 0.05},
                budget_chars=100, score_floor=0.35, max_item_chars=600)
    assert [k.key for k in kept] == ["a"]


def test_floor_is_skipped_when_no_scores_supplied():
    cands = [c("a", "aaa"), c("b", "bbb")]
    kept = pack(cands, {}, budget_chars=100, score_floor=0.35, max_item_chars=600)
    assert len(kept) == 2


def test_empty_scores_falls_back_to_priority_order():
    cands = [c("H1", "hist", priority=4, source="history"), c("U1", "prof", priority=1)]
    kept = pack(cands, {}, budget_chars=100, score_floor=0.0, max_item_chars=600)
    assert [k.key for k in kept] == ["U1", "H1"]


def test_oversized_item_is_truncated_to_max_item_chars_in_place():
    big = c("big", "z" * 1000)
    kept = pack([big], {}, budget_chars=2000, score_floor=0.0, max_item_chars=600)
    assert len(kept) == 1
    assert kept[0].chars == 600


def test_oversized_item_beyond_budget_is_dropped():
    big = c("big", "z" * 1000)
    kept = pack([big], {}, budget_chars=100, score_floor=0.0, max_item_chars=600)
    assert kept == []

# SPDX-License-Identifier: MIT
from __future__ import annotations

from src.memory.candidates import Candidate
from src.memory.pack import pack, render_slots


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


def test_render_groups_by_source_under_original_headers():
    kept = [
        Candidate("profile", "U1", "- 城市: 杭州", 1),
        Candidate("fact", "F1", "- 部署: /data", 0),
        Candidate("history", "H1", "- 上次改过挂载", 4),
    ]
    slots = render_slots(kept)
    assert "[Saved Facts]" in slots["memory"]
    assert "[User Profile]" in slots["memory"]
    assert slots["memory"].index("[Saved Facts]") < slots["memory"].index("[User Profile]")
    assert "- 部署: /data" in slots["memory"]
    assert slots["strategy"] == ""
    assert slots["experience"] == ""


def test_render_puts_strategy_and_experience_in_their_own_slots():
    kept = [
        Candidate("strategy", "S1", "- 先跑最小复现", 2),
        Candidate("experience", "E1", "- 群聊: per-scene cast", 3),
    ]
    slots = render_slots(kept)
    assert slots["memory"] == ""
    assert "- 先跑最小复现" in slots["strategy"]
    assert "- 群聊: per-scene cast" in slots["experience"]


def test_render_of_empty_selection_is_all_empty():
    slots = render_slots([])
    assert slots == {"memory": "", "strategy": "", "experience": ""}


def test_render_appends_unconditional_strategy_lines_under_one_header():
    kept = [Candidate("strategy", "S1", "- 先跑最小复现", 2)]
    slots = render_slots(kept, extra_strategy_lines=["- Avoid `run_command` (42% success)"])
    assert "run_command" in slots["strategy"]
    assert "先跑最小复现" in slots["strategy"]
    assert slots["strategy"].count("## Learned Strategies") == 1


def test_render_emits_strategy_slot_from_extra_lines_alone():
    slots = render_slots([], extra_strategy_lines=["- `run_command` is slow"])
    assert "## Learned Strategies" in slots["strategy"]
    assert "run_command" in slots["strategy"]


def test_unscored_items_keep_priority_order_and_skip_the_floor():
    """An item the judge never rated (dead batch, or no judge) must not be
    floor-dropped just because it has no score."""
    cands = [c("H1", "hist", priority=4, source="history"), c("U1", "prof", priority=1)]
    kept = pack(cands, {"U1": 0.1}, budget_chars=100, score_floor=0.35, max_item_chars=600)
    assert [k.key for k in kept] == ["H1"]


def test_drop_unscored_removes_items_the_judge_never_rated():
    cands = [c("U1", "prof", priority=1), c("H1", "hist", priority=4, source="history")]
    kept = pack(cands, {"U1": 0.9}, budget_chars=100, score_floor=0.0,
                max_item_chars=600, drop_unscored=True)
    assert [k.key for k in kept] == ["U1"]


def test_drop_unscored_with_no_scores_at_all_drops_everything():
    cands = [c("U1", "prof", priority=1), c("H1", "hist", priority=4, source="history")]
    assert pack(cands, {}, budget_chars=100, score_floor=0.0,
                max_item_chars=600, drop_unscored=True) == []


def test_render_emits_the_experience_contract_around_surviving_entries():
    kept = [Candidate("experience", "E1", "- 群聊: per-scene cast", 3)]
    slots = render_slots(
        kept, experience_header="## Experiences (MUST load)",
        experience_rule="[Skill loading rule] ...",
    )
    body = slots["experience"]
    assert "## Experiences (MUST load)" in body
    assert "- 群聊: per-scene cast" in body
    assert body.index("## Experiences") < body.index("[Skill loading rule]")


def test_render_omits_the_skill_rule_when_no_entry_survived():
    """The rule refers to the list above it, so it must never appear alone."""
    slots = render_slots(
        [], experience_header="## Experiences (MUST load)",
        experience_rule="[Skill loading rule] ...",
    )
    assert slots["experience"] == ""


def test_render_appends_extra_experience_blocks_after_the_contract():
    kept = [Candidate("experience", "E1", "- x", 3)]
    slots = render_slots(
        kept, extra_experience_blocks=["## Memory (2 chunks)\n- [s] t: b"],
    )
    body = slots["experience"]
    assert "## Memory (2 chunks)" in body
    assert body.index("## Experiences") < body.index("## Memory")


def test_render_emits_extra_experience_blocks_without_the_contract():
    slots = render_slots([], extra_experience_blocks=["## Memory (1 chunks)"])
    assert "## Memory" in slots["experience"]

# SPDX-License-Identifier: MIT
from __future__ import annotations

from src.memory.pipeline import InjectionPipeline
from src.memory.recall import RecallResult


class _Judge:
    def __init__(self, scores=None):
        self.scores = scores or {}
        self.seen = None
        self.seen_chars = 0
        self.mode = None
        self.context = None

    def score(self, query, candidates, *, mode, context=""):
        self.seen = [c.key for c in candidates]
        self.seen_chars = sum(c.chars for c in candidates)
        self.mode = mode
        self.context = context
        return self.scores


class _FakeStrategy:
    def __init__(self, lines=(), tool_stats=()):
        self._lines = list(lines)
        self._tool_stats = list(tool_stats)

    def item_lines(self):
        return self._lines

    def tool_stat_lines(self):
        return self._tool_stats


class _Exp:
    def __init__(self, name, description):
        self.name = name
        self.description = description
        self.category = "c"


class _FakeExpStore:
    def __init__(self, items=()):
        self._items = list(items)

    def list_for_index(self):
        return self._items


def _pipeline(judge, budget=80):
    return InjectionPipeline(
        judge=judge, budget_chars=budget, candidate_cap=40,
        score_floor=0.0, max_item_chars=600,
    )


def test_pipeline_falls_back_to_priority_without_scores():
    res = RecallResult(profile={"城市": "杭州"}, similar_conversations=[{"text": "历史"}])
    slots = _pipeline(_Judge()).build_slots("q", res, mode="agent")
    assert "[User Profile]" in slots["memory"]
    assert "[Relevant History]" in slots["memory"]


def test_pipeline_lets_judge_promote_history_past_the_budget():
    res = RecallResult(
        profile={"城市": "杭" * 40},
        similar_conversations=[{"text": "关键历史"}],
    )
    slots = _pipeline(_Judge({"H1": 0.9, "U1": 0.1})).build_slots("q", res, mode="agent")
    assert "关键历史" in slots["memory"]


def test_pipeline_judge_sees_all_sources_before_capping():
    res = RecallResult(
        profile={"a": "1"}, preferences={"b": "2"},
        patterns=[{"pattern": "p", "count": 1}],
        memory_chunks=[{"title": "t", "body": "b", "source": "s"}],
        similar_conversations=[{"text": "h"}],
    )
    judge = _Judge()
    _pipeline(judge).build_slots("q", res, mode="agent")
    assert judge.seen == ["F1", "U1", "R1", "T1", "H1"]


def test_pipeline_passes_mode_and_context_to_the_judge():
    judge = _Judge()
    _pipeline(judge).build_slots("q", RecallResult(), mode="character", context="Name: X")
    assert judge.mode == "character"
    assert judge.context == "Name: X"


def test_pipeline_includes_extra_sources_only_when_asked():
    judge = _Judge()
    _pipeline(judge).build_slots(
        "q", RecallResult(), mode="agent",
        experience_store=_FakeExpStore([_Exp("群聊", "per-scene cast")]),
        strategy_injector=_FakeStrategy(["- 先跑最小复现"]),
        include_extra=False,
    )
    assert judge.seen == []


def test_pipeline_gathers_strategy_and_experience_when_asked():
    judge = _Judge()
    slots = _pipeline(judge).build_slots(
        "q", RecallResult(), mode="agent",
        experience_store=_FakeExpStore([_Exp("群聊", "per-scene cast")]),
        strategy_injector=_FakeStrategy(["- 先跑最小复现"]),
    )
    assert "S1" in judge.seen
    assert "E1" in judge.seen
    assert "先跑最小复现" in slots["strategy"]
    assert "群聊" in slots["experience"]


def test_pipeline_places_tool_stats_unconditionally_bypassing_judgment():
    judge = _Judge({"S1": 0.0})
    slots = _pipeline(judge, budget=5).build_slots(
        "q", RecallResult(), mode="agent",
        strategy_injector=_FakeStrategy(
            ["- 先跑最小复现"], tool_stats=["- Avoid `run_command` (42% success)"],
        ),
    )
    assert "run_command" in slots["strategy"]


def test_no_output_is_ever_cut_mid_item():
    res = RecallResult(similar_conversations=[{"text": "x" * 500}])
    slots = _pipeline(_Judge()).build_slots("q", res, mode="agent")
    for line in slots["memory"].splitlines():
        if line.startswith("- "):
            assert line.endswith("x")


def test_judge_sees_more_than_the_budget_allows():
    """The judge must see candidates the budget cannot hold. Otherwise it only
    ever sees what priority order already let through — the original bug."""
    judge = _Judge()
    res = RecallResult(similar_conversations=[{"text": "z" * 300} for _ in range(20)])
    _pipeline(judge, budget=100).build_slots("q", res, mode="agent")
    assert len(judge.seen) == 20
    assert judge.seen_chars > 100

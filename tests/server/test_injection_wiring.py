# SPDX-License-Identifier: MIT
"""End-to-end wiring: the live engine's injection path assembles whole items.

tests/server/conftest.py stubs _memory_block/_strategy_block/_experience_block
for every test in this directory, so these drive _injection_slots directly and
neutralise the extra candidate sources themselves — otherwise real experience
rows would leak into the assertions.
"""
from __future__ import annotations

import pytest

from src.memory.recall import RecallResult
import src.server.ws_server as ws_mod


class _EmptyStore:
    def list_for_index(self):
        return []


class _NoJudge:
    """Deterministic stand-in for the real judge.

    The live engine builds an LlmJudge bound to whatever provider the user has
    configured, so leaving it in place would make these tests hit a real model:
    non-deterministic, and a network call the suite has no business making.
    """

    def score(self, query, candidates, *, mode, context=""):
        return {}


class _FixedJudge:
    def __init__(self, scores):
        self.scores = scores

    def score(self, query, candidates, *, mode, context=""):
        return dict(self.scores)


class _FakeStrategyInjector:
    def __init__(self, items=(), tool_stats=()):
        self._items = list(items)
        self._tool_stats = list(tool_stats)
        self.recent = None

    def set_recent_strategies(self, strategies):
        self.recent = list(strategies)

    def item_lines(self):
        return list(self._items)

    def tool_stat_lines(self):
        return list(self._tool_stats)


@pytest.fixture
def engine(monkeypatch):
    eng = ws_mod._engine
    monkeypatch.setattr(eng.injection_pipeline, "judge", _NoJudge())
    monkeypatch.setattr(eng.experience_injector, "store", _EmptyStore())
    monkeypatch.setattr(eng, "strategy_injector", _FakeStrategyInjector())
    monkeypatch.setattr(eng.reflection_store, "list_recent", lambda **k: [])
    monkeypatch.setattr(eng.session_store, "session_ids_for_character", lambda cid: set())
    return eng


def test_injected_items_are_never_cut_mid_line(engine, monkeypatch):
    profile = {f"k{i}": "v" * 40 for i in range(30)}
    history = [{"text": f"h{i}-" + "x" * 200} for i in range(10)]
    monkeypatch.setattr(
        engine.recall, "recall_for_context",
        lambda *a, **k: RecallResult(profile=profile, similar_conversations=history),
    )
    block = engine._injection_slots("q")["memory"]

    assert block
    assert "..." not in block  # no positional truncation marker survives
    for line in block.splitlines():
        if line.startswith("- "):
            assert line.endswith(("v", "x")), f"item was cut mid-line: {line!r}"


def test_budget_bounds_the_block(engine, monkeypatch):
    monkeypatch.setattr(
        engine.recall, "recall_for_context",
        lambda *a, **k: RecallResult(profile={f"k{i}": "v" * 40 for i in range(60)}),
    )
    body = engine._injection_slots("q")["memory"]

    # Candidate characters fit the budget; section headers add a small overhead.
    assert len(body) <= engine.config.inject_budget_chars + 200


def test_history_reaches_the_block_despite_lowest_priority(engine, monkeypatch):
    monkeypatch.setattr(
        engine.recall, "recall_for_context",
        lambda *a, **k: RecallResult(
            profile={f"k{i}": "v" * 40 for i in range(20)},
            similar_conversations=[{"text": f"h{i}-" + "x" * 100} for i in range(6)],
        ),
    )
    block = engine._injection_slots("q")["memory"]

    assert "[User Profile]" in block
    assert "[Relevant History]" in block


def test_tool_stats_bypass_the_budget_and_stay_in_the_strategy_slot(engine, monkeypatch):
    monkeypatch.setattr(
        engine, "strategy_injector",
        _FakeStrategyInjector(tool_stats=["- Avoid `run_command` (42% success over 18 uses)"]),
    )
    monkeypatch.setattr(engine.recall, "recall_for_context", lambda *a, **k: RecallResult())

    strategy = engine._injection_slots("q", include_experience=False)["strategy"]
    assert "run_command" in strategy
    assert strategy.count("## Learned Strategies") == 1


def test_memory_only_callers_skip_the_extra_sources(engine, monkeypatch):
    calls = {"n": 0}

    def _counting(intensity=None):
        calls["n"] += 1
        return _FakeStrategyInjector()

    monkeypatch.setattr(engine, "_strategy_injector_for", _counting)
    monkeypatch.setattr(engine.recall, "recall_for_context", lambda *a, **k: RecallResult())

    engine._injection_slots("q", include_strategy=False, include_experience=False)
    assert calls["n"] == 0


def test_asking_for_the_extra_sources_does_consult_the_strategy_injector(engine, monkeypatch):
    """Positive control for the test above: the counter can actually move."""
    calls = {"n": 0}

    def _counting(intensity=None):
        calls["n"] += 1
        return _FakeStrategyInjector()

    monkeypatch.setattr(engine, "_strategy_injector_for", _counting)
    monkeypatch.setattr(engine.recall, "recall_for_context", lambda *a, **k: RecallResult())

    engine._injection_slots("q")
    assert calls["n"] == 1


def test_floor_drops_low_scoring_items_before_packing(engine, monkeypatch):
    monkeypatch.setattr(
        engine.injection_pipeline, "judge",
        _FixedJudge({"U1": 0.9, "U2": 0.1, "H1": 0.05}),
    )
    monkeypatch.setattr(
        engine.recall, "recall_for_context",
        lambda *a, **k: RecallResult(
            profile={"k0": "v", "k1": "w"},
            similar_conversations=[{"text": "history-here"}],
        ),
    )
    block = engine._injection_slots("q")["memory"]

    assert "k0" in block
    assert "k1" not in block
    assert "[Relevant History]" not in block


def test_judge_rescues_history_when_the_budget_is_tight(engine, monkeypatch):
    monkeypatch.setattr(
        engine.injection_pipeline, "judge",
        _FixedJudge({"U1": 0.5, "U2": 0.5, "H1": 0.95}),
    )
    monkeypatch.setattr(engine.injection_pipeline, "budget_chars", 12)
    monkeypatch.setattr(
        engine.recall, "recall_for_context",
        lambda *a, **k: RecallResult(
            profile={"k0": "v" * 20, "k1": "w" * 20},
            similar_conversations=[{"text": "hist"}],
        ),
    )
    block = engine._injection_slots("q")["memory"]

    assert "hist" in block
    assert "k0" not in block


class _Exp:
    def __init__(self, name, description):
        self.name = name
        self.description = description
        self.category = "c"


class _StoreWith(_EmptyStore):
    def __init__(self, items):
        self._items = list(items)

    def list_for_index(self):
        return self._items


def test_agent_mode_is_not_judged_as_a_character(engine, monkeypatch):
    """Every prompt build resolves a default character, so keying the judge on
    `character is not None` ran the persona filter over agent turns too."""
    seen = {}

    class SpyJudge:
        def score(self, query, candidates, *, mode, context=""):
            seen["mode"] = mode
            seen["context"] = context
            return {}

    monkeypatch.setattr(engine.injection_pipeline, "judge", SpyJudge())
    monkeypatch.setattr(engine.recall, "recall_for_context", lambda *a, **k: RecallResult())

    engine._injection_slots("q", mode="agent", character=object())

    assert seen["mode"] == "agent"
    assert seen["context"] == ""  # no persona summary leaks into the agent judge


def test_agent_mode_keeps_memory_the_judge_did_not_rate(engine, monkeypatch):
    monkeypatch.setattr(engine.injection_pipeline, "judge", _NoJudge())
    monkeypatch.setattr(
        engine.recall, "recall_for_context",
        lambda *a, **k: RecallResult(profile={"city": "杭州"}),
    )
    slots = engine._injection_slots("q", mode="agent", character=object())
    assert "杭州" in slots["memory"]


def test_character_mode_drops_memory_the_judge_did_not_rate(engine, monkeypatch):
    monkeypatch.setattr(engine.injection_pipeline, "judge", _NoJudge())
    monkeypatch.setattr(
        engine.recall, "recall_for_context",
        lambda *a, **k: RecallResult(profile={"tool_strategy": "prefer chat.llm"}),
    )
    slots = engine._injection_slots("q", mode="character", character=object())
    assert slots["memory"] == ""


def test_experience_slot_carries_the_skill_loading_contract(engine, monkeypatch):
    monkeypatch.setattr(
        engine.experience_injector, "store",
        _StoreWith([_Exp("群聊", "per-scene cast")]),
    )
    monkeypatch.setattr(engine.recall, "recall_for_context", lambda *a, **k: RecallResult())

    body = engine._injection_slots("q")["experience"]

    assert "MUST call experience_view" in body
    assert "[Skill loading rule]" in body
    assert "群聊" in body


def test_experience_contract_absent_when_no_entry_survives(engine, monkeypatch):
    monkeypatch.setattr(engine.recall, "recall_for_context", lambda *a, **k: RecallResult())
    assert engine._injection_slots("q")["experience"] == ""


def test_refresh_rebuilds_the_pipeline(engine):
    before = engine.injection_pipeline
    engine.refresh_injection_pipeline()
    assert engine.injection_pipeline is not before

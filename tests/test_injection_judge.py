# SPDX-License-Identifier: MIT
from __future__ import annotations

from src.memory.candidates import Candidate
from src.memory.judge import JevJudge, LlmJudge, NullJudge


def test_null_judge_returns_empty_scores():
    cands = [Candidate("profile", "U1", "- 城市: 杭州", 1)]
    assert NullJudge().score("q", cands, mode="agent") == {}


def test_null_judge_makes_no_network_call(monkeypatch):
    import urllib.request

    def boom(*a, **k):
        raise AssertionError("NullJudge must not touch the network")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    assert NullJudge().score("q", [], mode="character") == {}


class _FakeJev:
    def __init__(self):
        self.states = []
        self.instructions = []

    def nouls(self, state, instructions):
        self.states.append(state)
        self.instructions.append(instructions)
        return {k: 0.7 for k in instructions}


def test_jev_judge_maps_scores_by_candidate_key():
    j = JevJudge(_FakeJev())
    cands = [Candidate("profile", "U1", "- 城市: 杭州", 1)]
    assert j.score("今天天气如何", cands, mode="agent") == {"U1": 0.7}


def test_jev_judge_carries_query_and_candidate_text_into_state():
    fake = _FakeJev()
    j = JevJudge(fake)
    cands = [Candidate("profile", "U1", "- 城市: 杭州", 1)]
    j.score("今天天气如何", cands, mode="agent")
    assert "今天天气如何" in fake.states[0]
    assert "- 城市: 杭州" in fake.states[0]


def test_jev_judge_character_mode_includes_character_summary():
    fake = _FakeJev()
    j = JevJudge(fake)
    cands = [Candidate("profile", "U1", "- 城市: 杭州", 1)]
    j.score("", cands, mode="character", context="Name: 阿岚\nPersonality: 冷淡")
    assert "阿岚" in fake.states[0]


def test_jev_judge_asks_different_questions_per_mode():
    fake = _FakeJev()
    j = JevJudge(fake)
    cands = [Candidate("profile", "U1", "- 城市: 杭州", 1)]
    j.score("q", cands, mode="agent")
    j.score("q", cands, mode="character")
    assert fake.instructions[0]["U1"] != fake.instructions[1]["U1"]


def test_jev_judge_skips_call_when_no_candidates():
    fake = _FakeJev()
    assert JevJudge(fake).score("q", [], mode="agent") == {}
    assert fake.states == []


def test_jev_judge_returns_empty_on_batch_failure_so_priority_order_applies():
    from src.providers.judge.client import BatchFailed

    class Broken:
        def nouls(self, state, instructions):
            raise BatchFailed("503")

    cands = [Candidate("profile", "U1", "- x", 1)]
    assert JevJudge(Broken()).score("q", cands, mode="agent") == {}


def test_llm_judge_returns_empty_when_no_provider_configured():
    cands = [Candidate("profile", "U1", "- x", 1)]
    assert LlmJudge(None, "", "").score("q", cands, mode="character") == {}


def test_llm_judge_marks_kept_candidates_and_uses_cache(monkeypatch):
    calls = []

    class _Msg:
        content = '{"keep": ["U1"]}'

    class _Choice:
        message = _Msg()

    class _Resp:
        choices = [_Choice()]

    def fake_chat_completion(*a, **k):
        calls.append(1)
        return _Resp()

    monkeypatch.setattr("src.memory.judge.chat_completion", fake_chat_completion)
    cache: dict = {}
    judge = LlmJudge(object(), "m", "p", cache=cache)
    cands = [
        Candidate("profile", "U1", "- 城市: 杭州", 1),
        Candidate("profile", "U2", "- 生日: 3 月 12 日", 1),
    ]
    assert judge.score("q", cands, mode="character", context="Name: X") == {"U1": 1.0, "U2": 0.0}
    assert len(calls) == 1
    judge.score("q", cands, mode="character", context="Name: X")
    assert len(calls) == 1  # second call served from cache


def test_llm_judge_distinguishes_characters_via_context(monkeypatch):
    calls = []

    class _Msg:
        content = '{"keep": ["U1"]}'

    class _Choice:
        message = _Msg()

    class _Resp:
        choices = [_Choice()]

    monkeypatch.setattr(
        "src.memory.judge.chat_completion",
        lambda *a, **k: (calls.append(1), _Resp())[1],
    )
    cache: dict = {}
    judge = LlmJudge(object(), "m", "p", cache=cache)
    cands = [Candidate("profile", "U1", "- 城市: 杭州", 1)]
    judge.score("q", cands, mode="character", context="Name: A")
    judge.score("q", cands, mode="character", context="Name: B")
    assert len(calls) == 2  # different characters must not share a cache entry


def test_llm_judge_returns_no_scores_on_failure(monkeypatch):
    """No scores, not wrong scores. The caller decides whether that means
    fall back to priority (agent) or inject nothing (character)."""
    def boom(*a, **k):
        raise RuntimeError("provider down")

    monkeypatch.setattr("src.memory.judge.chat_completion", boom)
    judge = LlmJudge(object(), "m", "p")
    cands = [Candidate("profile", "U1", "- x", 1)]
    assert judge.score("q", cands, mode="character", context="c") == {}

# SPDX-License-Identifier: MIT
from __future__ import annotations

from src.memory.candidates import Candidate
from src.memory.judge import NullJudge


def test_null_judge_returns_empty_scores():
    cands = [Candidate("profile", "U1", "- 城市: 杭州", 1)]
    assert NullJudge().score("q", cands, mode="agent") == {}


def test_null_judge_makes_no_network_call(monkeypatch):
    import urllib.request

    def boom(*a, **k):
        raise AssertionError("NullJudge must not touch the network")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    assert NullJudge().score("q", [], mode="character") == {}

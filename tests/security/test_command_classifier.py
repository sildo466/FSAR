# SPDX-License-Identifier: MIT
from __future__ import annotations

import asyncio

import pytest

import src.providers.judge.client  # noqa: F401  (so the patch target exists)
from src.security import command_classifier as cc


class _Config:
    """Stands in for FsarConfig: only the lookups the classifier makes."""

    def __init__(self, *, judge=None, active="prov", model="model-x",
                 enabled=True, threshold=0.7):
        self._judge = judge or {}
        self._active = active
        self._model = model
        self._enabled = enabled
        self._threshold = threshold

    def get_judge(self):
        return {"base_url": "", "api_key": "", "model": "", **self._judge}

    def get_active_provider(self):
        return {"model": self._model} if self._model else {}

    def get(self, key, default=None):
        if key == "llm.active":
            return self._active
        if key == "security.command_classifier.enabled":
            return self._enabled
        if key == "security.command_classifier.threshold":
            return self._threshold
        return default


def _run(monkeypatch, config, score, *, jev=True):
    """Drive judge() with a fake engine returning one score."""
    if jev:
        class _Jev:
            def __init__(self, *a, **k):
                pass

            def nouls(self, state, instructions):
                return {"C1": score}
        monkeypatch.setattr(
            "src.providers.judge.client.JevClient", _Jev, raising=False,
        )
    else:
        monkeypatch.setattr(
            cc.CommandClassifier, "_llm_score", lambda self, payload: score
        )
    return asyncio.run(cc.CommandClassifier(config).judge(
        tool="run_command", command="ls", intent="list the folder",
        boundary="/work",
    ))


def test_a_score_above_the_threshold_is_dangerous(monkeypatch):
    verdict = _run(monkeypatch, _Config(judge={"base_url": "u", "api_key": "k"}), 0.9)
    assert verdict.dangerous
    assert not verdict.unavailable
    assert verdict.engine == "jev"


def test_a_score_below_the_threshold_is_not(monkeypatch):
    verdict = _run(monkeypatch, _Config(judge={"base_url": "u", "api_key": "k"}), 0.1)
    assert not verdict.dangerous
    assert not verdict.unavailable


def test_the_llm_carries_it_when_jev_is_not_configured(monkeypatch):
    verdict = _run(monkeypatch, _Config(), 0.95, jev=False)
    assert verdict.dangerous
    assert verdict.engine == "llm"


def test_a_missing_intent_is_refused_without_asking_anyone(monkeypatch):
    called = []
    monkeypatch.setattr(
        cc.CommandClassifier, "_llm_score",
        lambda self, payload: called.append(1) or 0.0,
    )
    verdict = asyncio.run(cc.CommandClassifier(_Config()).judge(
        tool="run_command", command="ls", intent="   ", boundary="/work",
    ))
    assert verdict.dangerous
    assert not verdict.unavailable
    assert called == []


def test_an_engine_failure_blocks(monkeypatch):
    class _Boom:
        def __init__(self, *a, **k):
            pass

        def nouls(self, state, instructions):
            raise RuntimeError("network down")
    monkeypatch.setattr("src.providers.judge.client.JevClient", _Boom, raising=False)

    verdict = asyncio.run(cc.CommandClassifier(
        _Config(judge={"base_url": "u", "api_key": "k"}),
    ).judge(tool="run_command", command="ls", intent="list", boundary="/work"))

    assert verdict.dangerous
    assert verdict.unavailable


def test_a_disabled_classifier_says_so(monkeypatch):
    verdict = _run(monkeypatch, _Config(enabled=False), 0.99)
    assert not verdict.dangerous
    assert verdict.engine == "disabled"

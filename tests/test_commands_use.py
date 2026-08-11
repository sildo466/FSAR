# SPDX-License-Identifier: MIT
"""Regression: /use must split the experience name from a trailing task."""
from __future__ import annotations

import asyncio
from collections import OrderedDict, deque
from types import SimpleNamespace

import src.memory as memory_mod
from src.server.handlers import commands


class FakeStore:
    def __init__(self):
        self.exp = SimpleNamespace(name="web-design-skill")
        self.bumped: list[str] = []

    def get_by_name(self, name):
        return self.exp if name == "web-design-skill" else None

    def render_experience_body(self, exp):
        return f"rendered:{exp.name}"

    def bump_use(self, name):
        self.bumped.append(name)


class FakeEngine:
    def __init__(self):
        self._active_conv_id = "conv-1"
        self._short_cache: OrderedDict[str, deque] = OrderedDict()
        self._command_followup = None

    def active_conversation_id(self):
        return self._active_conv_id

    def _ensure_short(self, conv_id):
        if conv_id not in self._short_cache:
            self._short_cache[conv_id] = deque()


def _store(monkeypatch):
    store = FakeStore()
    monkeypatch.setattr(memory_mod, "ExperienceStore", lambda: store)
    return store


def test_use_splits_name_from_task(monkeypatch):
    _store(monkeypatch)
    engine = FakeEngine()

    result = asyncio.run(commands.execute(engine, "/use web-design-skill 做一个优秀动画的网页"))

    assert result.startswith("Loaded experience `web-design-skill`")
    assert "做一个优秀动画的网页" in result
    assert engine._command_followup == {
        "conversation_id": "conv-1",
        "task": "做一个优秀动画的网页",
    }
    assert engine._short_cache["conv-1"][0]["role"] == "system"
    assert "rendered:web-design-skill" in engine._short_cache["conv-1"][0]["content"]


def test_use_without_task_only_loads_context(monkeypatch):
    _store(monkeypatch)
    engine = FakeEngine()

    result = asyncio.run(commands.execute(engine, "/use web-design-skill"))

    assert result.startswith("Loaded experience `web-design-skill`")
    assert engine._command_followup is None
    assert engine._short_cache["conv-1"][0]["role"] == "system"


def test_use_not_found_reports_only_the_name_token(monkeypatch):
    _store(monkeypatch)
    engine = FakeEngine()

    result = asyncio.run(commands.execute(engine, "/use no-such-skill 任意任务"))

    assert result == "Not found: `no-such-skill` — list available ones with `/exp`."
    assert "no-such-skill 任意任务" not in result

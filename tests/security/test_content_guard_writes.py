# SPDX-License-Identifier: MIT
from __future__ import annotations

import time

import pytest

from src.security.content_guard import ContentGuard
from src.security.content_screen import ScreenVerdict


class _FakeConfig:
    def __init__(self, enabled=True):
        self._enabled = enabled

    def get(self, path, default=None):
        if path == "security.content_screening.enabled":
            return self._enabled
        if path == "security.content_screening.threshold":
            return 0.5
        return default

    def get_judge(self):
        return {}

    def get_active_provider(self):
        return {}


class _StubScreener:
    def __init__(self):
        self._jev = None

    def screen_batch(self, items, *, kind):
        return {
            k: (
                ScreenVerdict(flagged=True, confidence=0.99)
                if "EVIL" in t
                else ScreenVerdict(flagged=False, confidence=0.01)
            )
            for k, t in items.items()
        }


class _FakeAdapter:
    name = "chunk"

    def __init__(self):
        self.removed = []

    def enumerate(self):
        return []

    def remove(self, item):
        self.removed.append(item.record_ref)
        return True

    def restore(self, item, text):
        return True


@pytest.fixture
def guard(tmp_path):
    return ContentGuard(
        _FakeConfig(), screener=_StubScreener(), db_path=tmp_path / "m.db", autostart=False
    )


def test_submit_quarantines_flagged_text(guard):
    adapter = _FakeAdapter()
    guard.submit_for_test(
        adapter, store="chunk", record_ref="9", text="EVIL payload", kind="memory_chunk"
    )
    guard.flush_or_raise()
    assert adapter.removed == ["9"]
    assert guard.list_quarantine()[0]["text"] == "EVIL payload"


def test_submit_keeps_clean_text(guard):
    adapter = _FakeAdapter()
    guard.submit_for_test(
        adapter, store="chunk", record_ref="9", text="harmless", kind="memory_chunk"
    )
    guard.flush_or_raise()
    assert adapter.removed == []
    assert guard.list_quarantine() == []


def test_submit_is_noop_when_disabled(tmp_path):
    g = ContentGuard(
        _FakeConfig(enabled=False),
        screener=_StubScreener(),
        db_path=tmp_path / "m.db",
        autostart=False,
    )
    adapter = _FakeAdapter()
    g.submit_for_test(adapter, store="chunk", record_ref="9", text="EVIL", kind="memory_chunk")
    g.flush_or_raise()
    assert adapter.removed == []
    assert g.list_quarantine() == []


def test_submit_returns_immediately(guard):
    adapter = _FakeAdapter()
    started = time.monotonic()
    for i in range(200):
        guard.submit_for_test(
            adapter, store="chunk", record_ref=str(i), text="EVIL", kind="memory_chunk"
        )
    assert time.monotonic() - started < 1.0


def test_whitelisted_write_is_skipped(guard):
    adapter = _FakeAdapter()
    guard.add_to_whitelist("EVIL payload", added_by="restore")
    guard.submit_for_test(
        adapter, store="chunk", record_ref="9", text="EVIL payload", kind="memory_chunk"
    )
    guard.flush_or_raise()
    assert adapter.removed == []
    assert guard.list_quarantine() == []


def test_blank_text_is_skipped(guard):
    adapter = _FakeAdapter()
    guard.submit_for_test(adapter, store="chunk", record_ref="9", text="   ", kind="memory_chunk")
    guard.flush_or_raise()
    assert adapter.removed == []


def test_adapters_are_built_once(guard, monkeypatch):
    import src.security.content_guard as cg

    calls = []

    def _counting(cfg):
        calls.append(1)
        return []

    monkeypatch.setattr(cg, "default_adapters", _counting)
    guard.adapters()
    guard.adapters()
    assert len(calls) == 1


class _Recorder:
    enabled = True

    def __init__(self):
        self.calls = []

    def submit(self, **kwargs):
        self.calls.append(kwargs)


def test_store_write_hooks_route_through_the_guard(monkeypatch, tmp_path):
    from datetime import datetime

    from src.memory.experience_store import Experience, ExperienceStore
    from src.memory.reflection import ReflectionStore, TaskReflection
    from src.memory.user_model import UserModel
    from src.security import content_guard

    rec = _Recorder()
    monkeypatch.setattr(content_guard, "_GUARD", rec)
    db = tmp_path / "memory.db"

    UserModel(db).set_preference("editor", "nvim")
    UserModel(db).record_pattern("asks for markdown", "seen 3x")
    ExperienceStore(db).add_chunk(source="user_fact", title="t", body="b")
    ExperienceStore(db).upsert_experience(
        Experience(name="e1", category="c", description="d", body="b")
    )
    ReflectionStore(db).save(
        TaskReflection(
            task_id="t1",
            outcome="success",
            failure_modes=[],
            success_patterns=[],
            suggested_strategy="do the thing",
            step_count=1,
            tools_used=[],
            error_count=0,
            generated_at=datetime.now(),
        ),
        session_id="s1",
    )

    assert sorted(c["store"] for c in rec.calls) == [
        "chunk",
        "experience",
        "pattern",
        "preference",
        "reflection",
    ]


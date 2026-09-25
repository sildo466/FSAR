# SPDX-License-Identifier: MIT
from __future__ import annotations

import pytest

from src.notifications.store import NotificationStore
from src.server.handlers import notifications as handler
from src.updates.apply import UpdatePlan


class _FakeWS:
    def __init__(self):
        self.sent: list[dict] = []

    async def send_json(self, payload):
        self.sent.append(payload)


class _FakeConfig:
    def __init__(self, db_path):
        self._db = str(db_path)

    def get(self, key, default=None):
        if key == "memory.sqlite_path":
            return self._db
        return default


@pytest.fixture
def config(tmp_path):
    return _FakeConfig(tmp_path / "m.db")


async def test_apply_reports_refusal_without_raising(config, monkeypatch):
    def _refuse(*args, **kwargs):
        from src.updates.apply import UpdateRefused

        raise UpdateRefused("uncommitted changes would be lost: a.txt")

    monkeypatch.setattr("src.server.handlers.notifications.build_plan", _refuse)
    ws = _FakeWS()
    await handler.dispatch(ws, {"type": "updates.apply", "tag": "v0.7.0"}, config)
    payload = ws.sent[0]
    assert payload["type"] == "updates.apply_result"
    assert payload["ok"] is False
    assert "uncommitted" in payload["error"]


async def test_apply_runs_the_plan_and_reports_the_outcome(config, monkeypatch):
    plan = UpdatePlan(
        target_tag="v0.7.0", target_branch="main", current_tag="v0.6.0-beta1",
        current_branch="v0.6.0", steps=(), drop_branch="v0.6.0",
    )
    monkeypatch.setattr(
        "src.server.handlers.notifications.build_plan",
        lambda *a, **k: plan,
    )
    monkeypatch.setattr(
        "src.server.handlers.notifications.apply_plan",
        lambda *a, **k: {
            "tag": "v0.7.0", "branch": "main", "head": "abc123 init",
            "dropped_branch": None, "kept_branch": "v0.6.0",
        },
    )
    ws = _FakeWS()
    await handler.dispatch(ws, {"type": "updates.apply", "tag": "v0.7.0"}, config)
    payload = ws.sent[0]
    assert payload["ok"] is True
    assert payload["branch"] == "main"
    assert payload["kept_branch"] == "v0.6.0"


async def test_check_reports_counts(config, monkeypatch):
    store = NotificationStore(config.get("memory.sqlite_path"))
    monkeypatch.setattr(handler, "_store", lambda _cfg: store)

    async def _noop(*args, **kwargs):
        return {"added": 0, "announcements": 0}

    monkeypatch.setattr("src.server.handlers.notifications.run_update_checks", _noop)
    ws = _FakeWS()
    await handler.dispatch(ws, {"type": "updates.check"}, config)
    payload = ws.sent[0]
    assert payload["type"] == "updates.check_result"
    assert payload["added"] == 0
    assert payload["announcements"] == 0


async def test_check_reports_a_failure_instead_of_crashing(config, monkeypatch):
    async def _boom(*args, **kwargs):
        raise RuntimeError("no network")

    monkeypatch.setattr("src.server.handlers.notifications.run_update_checks", _boom)
    ws = _FakeWS()
    await handler.dispatch(ws, {"type": "updates.check"}, config)
    payload = ws.sent[0]
    assert payload["type"] == "updates.check_result"
    assert payload["added"] == 0
    assert "no network" in payload["error"]


async def test_apply_requires_a_tag(config):
    ws = _FakeWS()
    await handler.dispatch(ws, {"type": "updates.apply"}, config)
    assert ws.sent[0]["ok"] is False
    assert "tag" in ws.sent[0]["error"]

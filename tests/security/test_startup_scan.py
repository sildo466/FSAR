# SPDX-License-Identifier: MIT
from __future__ import annotations

import asyncio

import pytest


class _FakeConfig:
    def __init__(self, scan=True, judge=None):
        self._scan = scan
        self._judge = judge or {}

    def get(self, path, default=None):
        if path == "security.content_screening.scan_on_startup":
            return self._scan
        if path == "security.content_screening.enabled":
            return True
        return default

    def get_judge(self):
        return self._judge


class _StubGuard:
    def __init__(self):
        self.calls = []
        self.report = {"scanned": 1, "quarantined": 0, "unavailable": 0, "total": 1}

    def scan_all(self, *, mode="full"):
        self.calls.append(mode)
        return dict(self.report, mode=mode)


JEV = {"base_url": "http://x", "api_key": "k", "model": "typesafe/jev"}


def _run(monkeypatch, cfg, guard):
    from src.server import ws_server

    monkeypatch.setattr(ws_server, "_config", cfg)
    monkeypatch.setattr(ws_server, "_get_content_guard", lambda: guard)

    async def _go():
        task = ws_server.start_content_scan()
        if task is not None:
            await task
        return task

    return asyncio.run(_go())


def test_scan_with_jev_is_full(monkeypatch):
    guard = _StubGuard()
    assert _run(monkeypatch, _FakeConfig(judge=JEV), guard) is not None
    assert guard.calls == ["full"]


def test_scan_without_jev_is_incremental(monkeypatch):
    guard = _StubGuard()
    assert _run(monkeypatch, _FakeConfig(judge={}), guard) is not None
    assert guard.calls == ["incremental"]


def test_scan_with_partial_judge_config_is_incremental(monkeypatch):
    guard = _StubGuard()
    _run(monkeypatch, _FakeConfig(judge={"base_url": "http://x"}), guard)
    assert guard.calls == ["incremental"]


def test_scan_respects_config(monkeypatch):
    guard = _StubGuard()
    assert _run(monkeypatch, _FakeConfig(scan=False, judge=JEV), guard) is None
    assert guard.calls == []


def test_scan_survives_a_crashing_guard(monkeypatch):
    from src.server import ws_server

    class _Boom:
        def scan_all(self, *, mode="full"):
            raise RuntimeError("db locked")

    monkeypatch.setattr(ws_server, "_config", _FakeConfig(judge=JEV))
    monkeypatch.setattr(ws_server, "_get_content_guard", lambda: _Boom())

    async def _go():
        await ws_server.start_content_scan()

    asyncio.run(_go())


def test_template_ships_screening_enabled():
    """New deployments must have screening on without any user action."""
    import yaml
    from pathlib import Path

    template = Path(__file__).resolve().parents[2] / "config" / "fsar.yaml.template"
    data = yaml.safe_load(template.read_text(encoding="utf-8"))
    block = data["security"]["content_screening"]
    assert block["enabled"] is True
    assert block["scan_on_startup"] is True
    assert block["threshold"] == 0.5

# SPDX-License-Identifier: MIT
from __future__ import annotations

import pytest


class _FakeConfig:
    def __init__(self, scan=True):
        self._scan = scan

    def get(self, path, default=None):
        if path == "security.content_screening.scan_on_startup":
            return self._scan
        if path == "security.content_screening.enabled":
            return True
        return default


class _StubGuard:
    def __init__(self):
        self.calls = 0

    def scan_all(self):
        self.calls += 1
        return {"scanned": 1, "quarantined": 0, "unavailable": 0, "total": 1}


def test_start_scan_runs_off_the_event_loop(monkeypatch):
    from src.server import ws_server
    import asyncio

    guard = _StubGuard()
    monkeypatch.setattr(ws_server, "_config", _FakeConfig())
    monkeypatch.setattr(ws_server, "_get_content_guard", lambda: guard)

    async def _run():
        task = ws_server.start_content_scan()
        assert task is not None
        await task

    asyncio.run(_run())
    assert guard.calls == 1


def test_start_scan_respects_config(monkeypatch):
    from src.server import ws_server

    guard = _StubGuard()
    monkeypatch.setattr(ws_server, "_config", _FakeConfig(scan=False))
    monkeypatch.setattr(ws_server, "_get_content_guard", lambda: guard)

    assert ws_server.start_content_scan() is None
    assert guard.calls == 0


def test_start_scan_survives_a_crashing_guard(monkeypatch):
    from src.server import ws_server
    import asyncio

    class _Boom:
        def scan_all(self):
            raise RuntimeError("db locked")

    monkeypatch.setattr(ws_server, "_config", _FakeConfig())
    monkeypatch.setattr(ws_server, "_get_content_guard", lambda: _Boom())

    async def _run():
        task = ws_server.start_content_scan()
        await task

    asyncio.run(_run())


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


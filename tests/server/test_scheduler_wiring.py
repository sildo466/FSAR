# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import src.scheduler.service as sched_service
import src.server.ws_server as ws_mod


async def _noop_coro():
    return None


@pytest.fixture
def offline_scheduler(monkeypatch):
    engine = ws_mod._engine

    async def _noop_start(self):
        return None

    monkeypatch.setattr(sched_service.SchedulerService, "start", _noop_start)
    monkeypatch.setattr(engine.mcp, "start", lambda: _noop_coro())
    monkeypatch.setattr(engine, "_mcp_started", False, raising=False)
    monkeypatch.delattr(engine, "scheduler", raising=False)
    return engine


@pytest.mark.asyncio
async def test_start_mcp_wires_engine_registry_into_executor(offline_scheduler):
    """start_mcp must build the scheduler executor from the engine's own tool
    registry attribute, not the CLI's differently-named one."""
    engine = offline_scheduler

    await engine.start_mcp()

    assert engine.scheduler._executor._tools is engine.registry


def test_scheduler_rest_reads_engine_scheduler_attr(offline_scheduler, monkeypatch):
    """The REST handler resolves engine.scheduler, so ChatEngine must expose
    the scheduler under that exact name after startup."""
    monkeypatch.setattr(ws_mod._engine.card_repo, "seed_builtins_if_empty", lambda: 0)

    with TestClient(ws_mod.app) as client:
        resp = client.get("/api/scheduler/jobs")

    assert resp.status_code == 200


def test_scheduler_rest_returns_503_before_startup(monkeypatch):
    """Before start_mcp runs there is no scheduler; the handler must answer
    503 rather than crash with AttributeError."""
    from src.server.handlers import scheduler as sched_handler

    monkeypatch.delattr(ws_mod._engine, "scheduler", raising=False)
    sched_handler.set_engine(ws_mod._engine)
    client = TestClient(ws_mod.app)

    resp = client.get("/api/scheduler/jobs")

    assert resp.status_code == 503

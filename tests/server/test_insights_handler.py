# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def tmp_ctx(tmp_path: Path):
    db = tmp_path / "memory.db"
    ctx = {"db_path": str(db)}
    import src.server.handlers.insights as ins_mod
    importlib.reload(ins_mod)

    import src.server.ws_server as ws_mod
    importlib.reload(ws_mod)
    ws_mod._ctx = ctx
    return ctx, ws_mod, db


def test_insights_snapshot_returns_kpis(tmp_ctx):
    _, ws_mod, db = tmp_ctx
    from src.memory.decision_log import DecisionLog
    log = DecisionLog(db_path=str(db))
    log.record(task_id="t1", session_id="s", step_no=1, chosen_tool="file_ops",
               args_summary="q", latency_ms=100, success=True,
               prompt_tokens=500, completion_tokens=80)
    log.record(task_id="t2", session_id="s", step_no=1, chosen_tool="file_ops",
               args_summary="q", latency_ms=200, success=False, error_class="timeout",
               prompt_tokens=400, completion_tokens=50)

    client = TestClient(ws_mod.app)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "insights.get"})
        for _ in range(5):
            m = ws.receive_json()
            if m.get("type") == "insights.snapshot":
                k = m["kpis"]
                assert k["total_decisions"] == 2
                assert k["success_rate_pct"] == 50.0
                assert k["total_tokens"] == 1030
                assert k["total_prompt_tokens"] == 900
                assert k["total_completion_tokens"] == 130
                # tool_stats list contains file_ops
                tool_names = [t["tool_name"] for t in m["tool_stats"]]
                assert "file_ops" in tool_names
                # active_strategies is markdown string
                assert isinstance(m["active_strategies_markdown"], str)
                # recent_decisions is a list
                assert isinstance(m["recent_decisions"], list)
                return
        pytest.fail("insights.snapshot not received")


def test_insights_snapshot_empty_db(tmp_ctx):
    _, ws_mod, db = tmp_ctx
    client = TestClient(ws_mod.app)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "insights.get"})
        for _ in range(5):
            m = ws.receive_json()
            if m.get("type") == "insights.snapshot":
                assert m["kpis"]["total_decisions"] == 0
                assert m["kpis"]["success_rate_pct"] == 0
                assert m["tool_stats"] == []
                assert m["recent_decisions"] == []
                return
        pytest.fail("insights.snapshot not received")

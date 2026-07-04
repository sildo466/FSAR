# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def tmp_ctx(tmp_path: Path, monkeypatch):
    db = tmp_path / "memory.db"
    cache_db = tmp_path / "llm_cache.db"
    ctx = {"db_path": str(db), "cache_db_path": str(cache_db)}
    import src.server.handlers.usage as usage_mod
    importlib.reload(usage_mod)

    import src.server.ws_server as ws_mod
    importlib.reload(ws_mod)
    ws_mod._ctx = ctx
    return ctx, ws_mod


def test_usage_range_returns_snapshot(tmp_ctx):
    _, ws_mod = tmp_ctx
    from src.memory.decision_log import DecisionLog

    log = DecisionLog(db_path=str(tmp_ctx[0]["db_path"]))
    log.record(task_id="u1", session_id="s", step_no=1, chosen_tool="file_ops",
               args_summary="q", latency_ms=120, success=True,
               prompt_tokens=2000, completion_tokens=400)
    log.record(task_id="u2", session_id="s", step_no=1, chosen_tool="web_search",
               args_summary="q", latency_ms=80, success=True,
               prompt_tokens=800, completion_tokens=120, cached_tokens=500)

    client = TestClient(ws_mod.app)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "usage.range", "from": "2020-01-01", "to": "2099-12-31"})
        for _ in range(5):
            m = ws.receive_json()
            if m.get("type") == "usage.snapshot":
                k = m["kpis"]
                assert k["total_tokens"] == 3320
                assert k["cached_tokens"] == 500
                assert k["cache_hit_pct"] > 0
                tool_names = [t["tool"] for t in m["per_tool"]]
                assert "file_ops" in tool_names
                assert "web_search" in tool_names
                assert isinstance(m["cache"], dict)
                assert "l1_hit_rate" in m["cache"]
                return
        pytest.fail("usage.snapshot not received")

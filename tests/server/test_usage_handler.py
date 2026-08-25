# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def tmp_ctx(tmp_path: Path, monkeypatch):
    db = tmp_path / "memory.db"
    ctx = {"db_path": str(db)}
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
               args_summary="q", latency_ms=120, success=True)
    log.record(task_id="u2", session_id="s", step_no=1, chosen_tool="web_search",
               args_summary="q", latency_ms=80, success=True)

    import sqlite3
    from src.memory.integrations import _ensure_schema

    conn = sqlite3.connect(str(tmp_ctx[0]["db_path"]))
    _ensure_schema(conn)
    conn.executemany(
        "INSERT INTO llm_token_usage(ts,provider,model,input_tokens,output_tokens,"
        "cache_read_tokens,cache_creation_tokens,cost_usd) VALUES(?,?,?,?,?,?,?,?)",
        [
            ("2026-08-01T10:00:00", "p1", "m1", 100, 10, 50, 20, 0.001),
            ("2026-08-02T10:00:00", "p1", "m1", 200, 20, 100, 40, 0.002),
        ],
    )
    conn.commit()
    conn.close()

    client = TestClient(ws_mod.app)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "usage.range", "from": "2020-01-01", "to": "2099-12-31"})
        for _ in range(5):
            m = ws.receive_json()
            if m.get("type") == "usage.snapshot":
                k = m["kpis"]
                assert k["total_tokens"] == 100 + 10 + 50 + 20 + 200 + 20 + 100 + 40
                assert k["cached_tokens"] == 150
                assert k["cache_creation_tokens"] == 60
                assert k["cache_hit_pct"] == round(100.0 * 150 / (300 + 60 + 150), 1)
                assert k["estimated_cost_usd"] == 0.003
                tool_names = [t["tool"] for t in m["per_tool"]]
                assert "file_ops" in tool_names
                assert "web_search" in tool_names
                rows = m["per_provider"]
                assert len(rows) == 1
                assert rows[0]["cache_read_tokens"] == 150
                assert rows[0]["cache_hit_pct"] == k["cache_hit_pct"]
                return
        pytest.fail("usage.snapshot not received")
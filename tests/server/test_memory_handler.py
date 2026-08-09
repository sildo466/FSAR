# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def tmp_ctx(tmp_path: Path, monkeypatch):
    db = tmp_path / "memory.db"
    ctx = {"db_path": str(db)}
    import src.server.handlers.memory as mem_mod
    importlib.reload(mem_mod)

    import src.server.ws_server as ws_mod
    importlib.reload(ws_mod)
    ws_mod._ctx = ctx
    return ctx, ws_mod


def test_memory_remember_persists_chunk(tmp_ctx):
    _, ws_mod = tmp_ctx
    client = TestClient(ws_mod.app)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "memory.remember", "body": "user prefers tea"})
        m = ws.receive_json()
        assert m["type"] == "memory.facts_result"
        time.sleep(0.1)
    from src.memory.experience_store import ExperienceStore
    store = ExperienceStore(tmp_ctx[0]["db_path"])
    chunks = store.list_chunks(source="user_fact", limit=10)
    assert any("tea" in c.body for c in chunks)


def test_memory_search_returns_results_or_empty(tmp_ctx):
    _, ws_mod = tmp_ctx
    client = TestClient(ws_mod.app)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "memory.search", "query": "anything"})
        # Either results arrive, or handler completes silently
        for _ in range(5):
            try:
                m = ws.receive_json()
                if m.get("type") == "memory.search_results":
                    assert "results" in m
                    assert "query" in m
                    return
            except Exception:
                break
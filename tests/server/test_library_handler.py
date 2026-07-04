# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def tmp_ctx(tmp_path: Path, monkeypatch):
    db = tmp_path / "library.db"
    ctx = {"db_path": str(db)}
    import src.server.handlers.library as lib_mod
    importlib.reload(lib_mod)

    import src.server.ws_server as ws_mod
    importlib.reload(ws_mod)
    ws_mod._ctx = ctx
    return ctx, ws_mod


def test_library_create_and_list(tmp_ctx):
    _, ws_mod = tmp_ctx
    client = TestClient(ws_mod.app)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({
            "type": "library.create",
            "name": "test-exp",
            "category": "coding",
            "description": "test experience",
            "body": "# Goal\nTest.",
        })
        time.sleep(0.1)
        ws.send_json({"type": "library.list"})
        for _ in range(5):
            m = ws.receive_json()
            if m.get("type") == "library.list_result":
                names = [e["name"] for e in m["experiences"]]
                assert "test-exp" in names
                return


def test_library_archive(tmp_ctx):
    _, ws_mod = tmp_ctx
    client = TestClient(ws_mod.app)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({
            "type": "library.create",
            "name": "arch-me",
            "category": "misc",
            "body": "x",
        })
        time.sleep(0.1)
        ws.send_json({"type": "library.archive", "name": "arch-me"})
        time.sleep(0.1)
        ws.send_json({"type": "library.list"})
        for _ in range(10):
            m = ws.receive_json()
            if m.get("type") == "library.list_result":
                states = {e["name"]: e["state"] for e in m["experiences"]}
                assert states.get("arch-me") == "archived"
                return
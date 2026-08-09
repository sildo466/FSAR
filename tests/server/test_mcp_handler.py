# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _write_yaml(path: Path, *, with_mcp_servers: bool = True) -> Path:
    body = "llm:\n  active: \"\"\n  providers: []\n"
    if with_mcp_servers:
        body += (
            "mcp:\n"
            "  servers:\n"
            "    - name: filesystem\n"
            "      command: npx\n"
            "      args: [\"-y\", \"fs-mcp\"]\n"
            "      enabled: true\n"
            "      risk_level: MEDIUM\n"
            "    - name: disabled_one\n"
            "      command: npx\n"
            "      args: []\n"
            "      enabled: false\n"
            "      risk_level: HIGH\n"
        )
    path.write_text(body)
    return path


def _reload_with_config(cfg: Path, mcp_manager=None):
    import src.server.ws_server as ws_mod
    importlib.reload(ws_mod)
    from src.utils.fsar_config import FsarConfig
    ws_mod._config = FsarConfig(cfg)
    ws_mod._ctx["config"] = ws_mod._config
    if mcp_manager is not None:
        ws_mod._ctx["mcp_manager"] = mcp_manager
    return ws_mod


def test_mcp_list_returns_servers_from_config(tmp_path: Path):
    cfg = _write_yaml(tmp_path / "fsar.yaml")
    ws_mod = _reload_with_config(cfg, mcp_manager=None)

    client = TestClient(ws_mod.app)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()  # snapshot
        ws.receive_json()  # conversation.list
        ws.send_json({"type": "mcp.list"})
        m = ws.receive_json()
        assert m["type"] == "mcp.status"
        names = [s["name"] for s in m["servers"]]
        assert "filesystem" in names
        assert "disabled_one" in names


def test_mcp_toggle_flips_enabled_flag(tmp_path: Path):
    cfg = _write_yaml(tmp_path / "fsar.yaml")
    ws_mod = _reload_with_config(cfg, mcp_manager=None)

    client = TestClient(ws_mod.app)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()  # snapshot
        ws.receive_json()  # conversation.list
        ws.send_json({"type": "mcp.toggle", "server_name": "filesystem", "enabled": False})
        m = ws.receive_json()
        assert m["type"] == "mcp.status"
        server = next(s for s in m["servers"] if s["name"] == "filesystem")
        assert server["enabled"] is False

    text = cfg.read_text()
    assert "enabled: false" in text


def test_mcp_reload_invokes_manager_reload(tmp_path: Path):
    cfg = _write_yaml(tmp_path / "fsar.yaml")

    class FakeManager:
        def __init__(self):
            self.reloaded = False

        async def reload(self):
            self.reloaded = True

        @property
        def servers(self):
            return ["filesystem"]

        def list_visible_tools(self):
            return []

    mgr = FakeManager()
    ws_mod = _reload_with_config(cfg, mcp_manager=mgr)

    client = TestClient(ws_mod.app)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()  # snapshot
        ws.receive_json()  # conversation.list
        ws.send_json({"type": "mcp.reload"})
        m = ws.receive_json()
        assert m["type"] == "mcp.status"
        assert "filesystem" in [s["name"] for s in m["servers"]]
    assert mgr.reloaded is True

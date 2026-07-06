# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib
import time
from pathlib import Path

from fastapi.testclient import TestClient


def _write_yaml(path: Path) -> Path:
    path.write_text("permissions:\n  mode: normal\n  tools: {}\n  path_rules: []\n")
    return path


def _reload_with_config(cfg: Path):
    import src.server.ws_server as ws_mod
    importlib.reload(ws_mod)
    from src.utils.fsar_config import FsarConfig
    ws_mod._config = FsarConfig(cfg)
    ws_mod._ctx["config"] = ws_mod._config
    return ws_mod


def test_permissions_patch_updates_yaml(tmp_path: Path):
    cfg = _write_yaml(tmp_path / "fsar.yaml")
    ws_mod = _reload_with_config(cfg)

    client = TestClient(ws_mod.app)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "permissions.patch", "patch": {
            "permissions.tools.run_command.mode": "trust",
        }})
        m = ws.receive_json()
        assert m["type"] == "settings.changed"
        time.sleep(0.05)

    text = cfg.read_text()
    assert "run_command" in text
    assert "trust" in text


def test_permissions_patch_rejects_non_dict(tmp_path: Path):
    cfg = _write_yaml(tmp_path / "fsar.yaml")
    ws_mod = _reload_with_config(cfg)

    client = TestClient(ws_mod.app)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "permissions.patch", "patch": "string-not-allowed"})
        m = ws.receive_json()
        assert m["type"] == "error"
    assert "trust" not in cfg.read_text()

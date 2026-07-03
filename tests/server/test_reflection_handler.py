# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib
import time
from pathlib import Path

from fastapi.testclient import TestClient


def _reload_with_config(cfg: Path):
    import src.server.ws_server as ws_mod
    importlib.reload(ws_mod)
    from src.utils.fsar_config import FsarConfig
    ws_mod._config = FsarConfig(cfg)
    return ws_mod


def _write_yaml(path: Path) -> Path:
    path.write_text(
        "reflection:\n"
        "  intensity: medium\n"
        "  triggers:\n"
        "    per_task: true\n"
        "    on_failure: true\n"
        "    idle_batch:\n"
        "      enabled: false\n"
        "      threshold_events: 20\n"
        "      threshold_hours: 12\n"
    )
    return path


def test_set_intensity_persists(tmp_path: Path):
    cfg = _write_yaml(tmp_path / "fsar.yaml")
    ws_mod = _reload_with_config(cfg)

    client = TestClient(ws_mod.app)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()  # snapshot
        ws.send_json({"type": "reflection.set_intensity", "intensity": "high"})
        time.sleep(0.1)
    assert "high" in cfg.read_text()


def test_set_intensity_rejects_bad_value(tmp_path: Path):
    cfg = _write_yaml(tmp_path / "fsar.yaml")
    ws_mod = _reload_with_config(cfg)

    client = TestClient(ws_mod.app)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "reflection.set_intensity", "intensity": "ultra"})
        time.sleep(0.1)
    assert "ultra" not in cfg.read_text()
    assert "medium" in cfg.read_text()

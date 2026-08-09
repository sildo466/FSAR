# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib
import time
from pathlib import Path

from fastapi.testclient import TestClient


def _write_yaml(path: Path) -> Path:
    path.write_text(
        "llm:\n"
        "  active: \"\"\n"
        "  providers: []\n"
        "ui:\n"
        "  theme: system\n"
    )
    return path


def _reload_with_config(cfg: Path):
    import src.server.ws_server as ws_mod
    importlib.reload(ws_mod)
    from src.utils.fsar_config import FsarConfig
    ws_mod._config = FsarConfig(cfg)
    return ws_mod


def test_settings_get_returns_config_snapshot(tmp_path: Path):
    cfg = _write_yaml(tmp_path / "fsar.yaml")
    ws_mod = _reload_with_config(cfg)

    client = TestClient(ws_mod.app)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()  # initial snapshot
        ws.receive_json()  # conversation.list
        ws.send_json({"type": "settings.get"})
        m = ws.receive_json()
        assert m["type"] == "snapshot"
        assert m["config"]["ui"]["theme"] == "system"


def test_settings_patch_persists_to_yaml(tmp_path: Path):
    cfg = _write_yaml(tmp_path / "fsar.yaml")
    ws_mod = _reload_with_config(cfg)

    client = TestClient(ws_mod.app)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "settings.patch", "patch": {"ui.theme": "dark", "ui.density": "compact"}})
        time.sleep(0.1)

    text = cfg.read_text()
    assert "dark" in text
    assert "compact" in text


def test_settings_patch_broadcasts_changed(tmp_path: Path):
    cfg = _write_yaml(tmp_path / "fsar.yaml")
    ws_mod = _reload_with_config(cfg)

    client = TestClient(ws_mod.app)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()  # snapshot
        ws.receive_json()  # conversation.list
        ws.send_json({"type": "settings.patch", "patch": {"ui.theme": "light"}})
        m = ws.receive_json()
        assert m["type"] == "settings.changed"
        assert m["patch"] == {"ui.theme": "light"}
        assert m["by"] == "user"


def test_llm_set_active_persists_and_broadcasts(tmp_path: Path):
    cfg_path = tmp_path / "fsar.yaml"
    cfg_path.write_text(
        "llm:\n"
        "  active: \"\"\n"
        "  providers:\n"
        "    - id: a\n"
        "      label: A\n"
        "      model: model-a\n"
        "      enabled: true\n"
        "    - id: b\n"
        "      label: B\n"
        "      model: model-b\n"
        "      enabled: true\n"
    )
    ws_mod = _reload_with_config(cfg_path)

    client = TestClient(ws_mod.app)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()  # snapshot
        ws.receive_json()  # conversation.list
        ws.send_json({"type": "llm.set_active", "provider_id": "b"})
        m = ws.receive_json()
        assert m["type"] == "llm.provider_changed"
        assert m["provider_id"] == "b"
        assert m["model"] == "model-b"

    assert "active: b" in cfg_path.read_text()

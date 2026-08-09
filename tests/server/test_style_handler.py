# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib
from pathlib import Path

from fastapi.testclient import TestClient


def _write_yaml(path: Path) -> Path:
    path.write_text("style:\n  theme: system\n  font_scale: 1.0\n  density: comfortable\n  motion: subtle\n")
    return path


def _reload_with_config(cfg: Path):
    import src.server.ws_server as ws_mod
    importlib.reload(ws_mod)
    from src.utils.fsar_config import FsarConfig
    ws_mod._config = FsarConfig(cfg)
    ws_mod._ctx["config"] = ws_mod._config
    return ws_mod


def test_style_patch_persists(tmp_path: Path):
    cfg = _write_yaml(tmp_path / "fsar.yaml")
    ws_mod = _reload_with_config(cfg)

    client = TestClient(ws_mod.app)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()  # snapshot
        ws.receive_json()  # conversation.list
        ws.send_json({"type": "style.patch", "patch": {"density": "compact", "font_scale": 1.15}})
        m = ws.receive_json()
        assert m["type"] == "style.changed"
        assert m["style"]["density"] == "compact"

    text = cfg.read_text()
    assert "compact" in text
    assert "1.15" in text


def test_style_set_theme_validates(tmp_path: Path):
    cfg = _write_yaml(tmp_path / "fsar.yaml")
    ws_mod = _reload_with_config(cfg)

    client = TestClient(ws_mod.app)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()  # snapshot
        ws.receive_json()  # conversation.list
        ws.send_json({"type": "style.set_theme", "theme": "neon"})
        m = ws.receive_json()
        assert m["type"] == "error"
        ws.send_json({"type": "style.set_theme", "theme": "dark"})
        m = ws.receive_json()
        assert m["type"] == "style.changed"
        assert m["style"]["theme"] == "dark"

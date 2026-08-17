# SPDX-License-Identifier: MIT
from __future__ import annotations

import importlib
import json
from pathlib import Path

from fastapi.testclient import TestClient

WARM = {"id": "warm", "name": "暖阳", "base": "light", "palette": {"bg": "#faf8f5", "accent": "#d4a04a"}}
NIGHT = {"id": "night", "name": "暗紫", "base": "dark", "palette": {"bg": "#14121a"}}


def _setup(tmp_path: Path):
    skins = tmp_path / "skins"
    for payload in (WARM, NIGHT):
        d = skins / payload["id"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "skin.json").write_text(json.dumps(payload), encoding="utf-8")
    cfg = tmp_path / "fsar.yaml"
    cfg.write_text(f"data:\n  skins_dir: {skins.as_posix()}\n", encoding="utf-8")
    import src.server.ws_server as ws_mod
    importlib.reload(ws_mod)
    from src.utils.fsar_config import FsarConfig
    ws_mod._config = FsarConfig(cfg)
    ws_mod._ctx["config"] = ws_mod._config
    return ws_mod


def test_skin_list_returns_presets(tmp_path: Path):
    ws_mod = _setup(tmp_path)
    client = TestClient(ws_mod.app)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()  # snapshot
        ws.receive_json()  # conversation.list
        ws.send_json({"type": "skin.list"})
        m = ws.receive_json()
        assert m["type"] == "skin.list"
        assert {s["id"] for s in m["skins"]} == {"warm", "night"}


def test_set_active_persists_and_validates(tmp_path: Path):
    ws_mod = _setup(tmp_path)
    client = TestClient(ws_mod.app)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.receive_json()
        ws.send_json({"type": "skin.set_active", "skin_id": "warm"})
        assert ws.receive_json() == {"type": "skin.changed", "skin_id": "warm"}
        assert ws_mod._config.get("style.skin_id") == "warm"
        ws.send_json({"type": "skin.set_active", "skin_id": "neon"})
        m = ws.receive_json()
        assert m["type"] == "error" and m["code"] == "bad_skin"
        assert ws_mod._config.get("style.skin_id") == "warm"


def test_snapshot_carries_skin_id(tmp_path: Path):
    ws_mod = _setup(tmp_path)
    ws_mod._config.patch("style.skin_id", "night")
    ws_mod._config.save()
    client = TestClient(ws_mod.app)
    with client.websocket_connect("/ws") as ws:
        snap = ws.receive_json()
        assert snap["type"] == "snapshot"
        assert snap["skin_id"] == "night"


def _png_bytes() -> bytes:
    from io import BytesIO
    from PIL import Image
    out = BytesIO()
    Image.new("RGB", (32, 24), color=(12, 34, 56)).save(out, format="PNG")
    return out.getvalue()


def test_skin_asset_route_serves_and_guards(tmp_path: Path, monkeypatch):
    ws_mod = _setup(tmp_path)
    home = tmp_path / "home"
    monkeypatch.setattr(ws_mod, "get_fsar_home", lambda: home)
    client = TestClient(ws_mod.app)

    repo_asset = tmp_path / "skins" / "warm" / "assets"
    repo_asset.mkdir(parents=True, exist_ok=True)
    (repo_asset / "bg.png").write_bytes(_png_bytes())
    home_asset = home / "data" / "skins" / "warm" / "assets"
    home_asset.mkdir(parents=True, exist_ok=True)
    home_png = b"HOME-" + _png_bytes()
    (home_asset / "bg.png").write_bytes(home_png)

    # home wins when present in both
    ok = client.get("/skin-assets/warm/bg.png")
    assert ok.status_code == 200
    assert ok.content == home_png

    # repo fallback when home missing
    (home_asset / "bg.png").unlink()
    ok2 = client.get("/skin-assets/warm/bg.png")
    assert ok2.status_code == 200
    assert ok2.content == _png_bytes()

    # missing + traversal blocked
    assert client.get("/skin-assets/warm/nope.png").status_code == 404
    assert client.get("/skin-assets/warm/%2e%2e/skin.json").status_code == 404

# SPDX-License-Identifier: MIT
from __future__ import annotations

from fastapi.testclient import TestClient

import src.server.ws_server as ws_mod


def _make_models_dir(tmp_path):
    models = tmp_path / "data" / "models"
    models.mkdir(parents=True, exist_ok=True)
    (models / "girl.vrm").write_bytes(b"VRM-BYTES")
    (models / "note.txt").write_bytes(b"not a model")
    return models


def test_models_list_lists_only_vrm(tmp_path, monkeypatch):
    _make_models_dir(tmp_path)
    monkeypatch.setattr(
        "src.utils.fsar_home.get_fsar_home", lambda: tmp_path
    )
    client = TestClient(ws_mod.app)
    resp = client.get("/api/models")
    assert resp.status_code == 200
    assert resp.json() == {"models": ["girl.vrm"]}


def test_models_download_returns_file(tmp_path, monkeypatch):
    _make_models_dir(tmp_path)
    monkeypatch.setattr(
        "src.utils.fsar_home.get_fsar_home", lambda: tmp_path
    )
    client = TestClient(ws_mod.app)
    resp = client.get("/api/models/girl.vrm")
    assert resp.status_code == 200
    assert resp.content == b"VRM-BYTES"


def test_models_download_404_for_unknown(tmp_path, monkeypatch):
    _make_models_dir(tmp_path)
    monkeypatch.setattr(
        "src.utils.fsar_home.get_fsar_home", lambda: tmp_path
    )
    client = TestClient(ws_mod.app)
    assert client.get("/api/models/nope.vrm").status_code == 404


def test_models_download_gate_refuses_non_vrm(tmp_path, monkeypatch):
    _make_models_dir(tmp_path)
    monkeypatch.setattr(
        "src.utils.fsar_home.get_fsar_home", lambda: tmp_path
    )
    client = TestClient(ws_mod.app)
    # only .vrm files are exposed, even ones sitting in the models dir
    assert client.get("/api/models/note.txt").status_code == 400


def test_models_list_includes_model3_json_recursive(tmp_path, monkeypatch):
    root = tmp_path / "data" / "models"
    root.mkdir(parents=True, exist_ok=True)
    (root / "girl.vrm").write_bytes(b"VRM-BYTES")
    sub = root / "hiyori"
    sub.mkdir(parents=True, exist_ok=True)
    (sub / "hiyori.model3.json").write_bytes(b'{"Version":3}')
    (sub / "texture_00.png").write_bytes(b"PNG")
    (root / "note.txt").write_bytes(b"not a model")
    monkeypatch.setattr("src.utils.fsar_home.get_fsar_home", lambda: tmp_path)
    client = TestClient(ws_mod.app)
    resp = client.get("/api/models")
    assert resp.status_code == 200
    assert resp.json() == {"models": ["girl.vrm", "hiyori/hiyori.model3.json"]}


def test_models_download_serves_live2d_assets(tmp_path, monkeypatch):
    sub = tmp_path / "data" / "models" / "hiyori"
    sub.mkdir(parents=True, exist_ok=True)
    (sub / "hiyori.model3.json").write_bytes(b'{"Version":3}')
    (sub / "hiyori.moc3").write_bytes(b"MOC3")
    monkeypatch.setattr("src.utils.fsar_home.get_fsar_home", lambda: tmp_path)
    client = TestClient(ws_mod.app)
    assert client.get("/api/models/hiyori/hiyori.model3.json").status_code == 200
    assert client.get("/api/models/hiyori/hiyori.moc3").status_code == 200


def test_models_download_still_refuses_txt_and_traversal(tmp_path, monkeypatch):
    root = tmp_path / "data" / "models"
    root.mkdir(parents=True, exist_ok=True)
    (root / "note.txt").write_bytes(b"not a model")
    monkeypatch.setattr("src.utils.fsar_home.get_fsar_home", lambda: tmp_path)
    client = TestClient(ws_mod.app)
    assert client.get("/api/models/note.txt").status_code == 400
    assert client.get("/api/models/%2e%2e/ws_server.py").status_code == 400
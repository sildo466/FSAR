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
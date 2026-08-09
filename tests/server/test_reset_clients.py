# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib

import src.utils.llm_factory as lf


def test_reset_clients_clears_all_three_caches(monkeypatch):
    """reset_clients must clear OpenAI, Gemini, AND Anthropic caches so a
    later provider switch can rebuild fresh clients."""
    lf._CLIENTS["x"] = object()
    lf._GEMINI_CLIENTS["y"] = object()
    lf._ANTHROPIC_CLIENTS["z"] = object()

    lf.reset_clients()

    assert lf._CLIENTS == {}
    assert lf._GEMINI_CLIENTS == {}
    assert lf._ANTHROPIC_CLIENTS == {}


def test_chat_done_provider_changed_resets_clients(tmp_path, monkeypatch):
    """When the WS broadcasts llm.provider_changed, ws_server (or its
    listener) must call reset_clients() so the next chat.send rebuilds."""
    import src.utils.llm_factory as lf2

    cfg = tmp_path / "fsar.yaml"
    cfg.write_text(
        "llm:\n"
        "  active: \"\"\n"
        "  providers:\n"
        "    - id: p1\n"
        "      label: P1\n"
        "      model: m1\n"
        "      enabled: true\n"
    )
    import src.server.ws_server as ws_mod
    importlib.reload(ws_mod)
    from src.utils.fsar_config import FsarConfig
    ws_mod._config = FsarConfig(cfg)
    lf2._CLIENTS["p1"] = object()
    assert lf2._CLIENTS

    from fastapi.testclient import TestClient

    client = TestClient(ws_mod.app)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "llm.set_active", "provider_id": "p1"})
        ws.receive_json()  # llm.provider_changed

    assert lf2._CLIENTS == {}

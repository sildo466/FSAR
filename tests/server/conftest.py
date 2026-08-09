# SPDX-License-Identifier: MIT
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolate_engine(monkeypatch):
    """Keep server tests offline: no MCP subprocesses, no embedder HTTP calls."""
    import src.server.ws_server as ws_mod
    from starlette.testclient import TestClient

    original_connect = TestClient.websocket_connect

    def authenticated_connect(client, url, subprotocols=None, **kwargs):
        headers = dict(kwargs.pop("headers", {}) or {})
        headers.setdefault("origin", "http://127.0.0.1:8765")
        headers.setdefault("host", "127.0.0.1:8765")
        protocols = subprotocols or ["fsar-v1", ws_mod._ws_auth.ensure_token()]
        return original_connect(
            client,
            url,
            subprotocols=protocols,
            headers=headers,
            **kwargs,
        )

    monkeypatch.setattr(TestClient, "websocket_connect", authenticated_connect)
    engine = ws_mod._engine
    from src.memory.cards import CharacterCard
    monkeypatch.setattr(
        engine.card_repo,
        "get_default_character",
        lambda: CharacterCard(
            id=1, name="Test Assistant", description="",
            personality="Helpful and concise.", scenario="", is_default=1,
            created_by="builtin",
        ),
    )
    monkeypatch.setattr(engine, "_mcp_started", True)
    monkeypatch.setattr(engine, "_memory_block", lambda *a, **k: "")
    monkeypatch.setattr(engine, "_strategy_block", lambda *a, **k: "")
    monkeypatch.setattr(engine, "_experience_block", lambda *a, **k: "")
    monkeypatch.setattr(engine, "_save_user", lambda *a, **k: None)
    monkeypatch.setattr(engine, "_save_assistant", lambda *a, **k: None)
    monkeypatch.setattr(engine, "_reflect", lambda *a, **k: None)
    yield

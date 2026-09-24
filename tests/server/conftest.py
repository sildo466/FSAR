# SPDX-License-Identifier: MIT
from __future__ import annotations

import pytest


class _EmptyStore:
    def list_for_index(self):
        return []

    def render_memory_chunks_block(self, *, limit: int = 5):
        return ""


class _EmptyStrategy:
    def set_recent_strategies(self, strategies):
        pass

    def item_lines(self):
        return []

    def tool_stat_lines(self):
        return []


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
    # Prompt assembly reaches memory through _injection_slots, so the hazards to
    # block are its dependencies — the judge (which calls the configured
    # provider) and recall (which reads the real DB) — not the older per-block
    # helpers, which nothing calls any more.
    from src.memory.judge import NullJudge
    from src.memory.recall import RecallResult

    monkeypatch.setattr(engine.injection_pipeline, "judge", NullJudge())
    monkeypatch.setattr(
        engine.recall, "recall_for_context", lambda *a, **k: RecallResult()
    )
    monkeypatch.setattr(engine.experience_injector, "store", _EmptyStore())
    monkeypatch.setattr(engine, "strategy_injector", _EmptyStrategy())
    monkeypatch.setattr(engine.reflection_store, "list_recent", lambda **k: [])
    monkeypatch.setattr(
        engine.session_store, "session_ids_for_character", lambda cid: set()
    )
    monkeypatch.setattr(engine, "_save_user", lambda *a, **k: None)
    monkeypatch.setattr(engine, "_save_assistant", lambda *a, **k: None)
    monkeypatch.setattr(engine, "_reflect", lambda *a, **k: None)
    yield

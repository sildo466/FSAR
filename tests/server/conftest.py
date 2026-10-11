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
    """Keep server tests offline: no MCP subprocesses, no embedder HTTP calls.

    The GUI's endpoints want a loopback peer, a same-origin origin and a
    session, so the default test client arrives as one. A test that wants to
    observe a refusal says so explicitly: TestClient(..., cookies={}) for "no
    session", TestClient(..., client=("203.0.113.7", 40000)) for "not this
    machine".
    """
    import src.server.ws_server as ws_mod
    from src.security.admin_session import ADMIN_COOKIE
    from starlette.testclient import TestClient

    # A refused handshake counts toward the per-address rate limit, which lives
    # on the process-wide boundary object. Without this, the refusals a test
    # makes lock out the next test connecting from the same address.
    ws_mod._ws_auth._failures.clear()

    original_connect = TestClient.websocket_connect
    original_init = TestClient.__init__

    def authenticated_connect(client, url, subprotocols=None, **kwargs):
        headers = dict(kwargs.pop("headers", {}) or {})
        headers.setdefault("origin", "http://127.0.0.1:8765")
        headers.setdefault("host", "127.0.0.1:8765")
        if subprotocols is None:
            session = ws_mod._admin_sessions.create_session()
            subprotocols = ["fsar-v1", ws_mod._admin_sessions.issue_ticket(session)]
        return original_connect(
            client,
            url,
            subprotocols=subprotocols,
            headers=headers,
            **kwargs,
        )

    def gui_client(self, app, **kwargs):
        kwargs.setdefault("base_url", "https://127.0.0.1:8765")
        kwargs.setdefault("client", ("127.0.0.1", 40000))
        headers = {"origin": "http://127.0.0.1:8765"}
        headers.update(kwargs.pop("headers", {}) or {})
        kwargs["headers"] = headers
        if "cookies" not in kwargs:
            kwargs["cookies"] = {
                ADMIN_COOKIE: ws_mod._admin_sessions.create_session()
            }
        original_init(self, app, **kwargs)

    monkeypatch.setattr(TestClient, "websocket_connect", authenticated_connect)
    monkeypatch.setattr(TestClient, "__init__", gui_client)
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
    from src.memory.pipeline import InjectionPipeline
    from src.memory.recall import RecallResult

    def _offline_pipeline() -> InjectionPipeline:
        """Every (re)build must be offline too: patching only the live instance
        would let refresh_injection_pipeline construct a real judge."""
        return InjectionPipeline(
            judge=NullJudge(),
            budget_chars=engine.config.inject_budget_chars,
            candidate_cap=engine.config.inject_candidate_cap,
            score_floor=engine.config.inject_score_floor,
            max_item_chars=engine.config.inject_max_item_chars,
        )

    monkeypatch.setattr(engine, "_build_injection_pipeline", _offline_pipeline)
    monkeypatch.setattr(engine, "injection_pipeline", _offline_pipeline())
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
    # The startup scan would build the real guard and call the configured
    # provider. tests/conftest.py already neutralises the write hooks; this
    # stops the scan itself.
    monkeypatch.setattr(ws_mod, "start_content_scan", lambda: None)
    # The birthday hook runs on every connect and saves the real config when it
    # fires, so a developer whose birthday happens to be today would have their
    # own fsar.yaml rewritten by the test run.
    monkeypatch.setattr(
        ws_mod, "_birthday_connect_payload",
        lambda config: {"letter": None, "skin_id": None, "letters": False},
    )
    yield

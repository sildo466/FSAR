# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolate_engine(monkeypatch):
    """Keep server tests offline: no MCP subprocesses, no embedder HTTP calls."""
    import src.server.ws_server as ws_mod

    engine = ws_mod._engine
    monkeypatch.setattr(engine, "_mcp_started", True)
    monkeypatch.setattr(engine, "_memory_block", lambda q: "")
    monkeypatch.setattr(engine, "_strategy_block", lambda: "")
    monkeypatch.setattr(engine, "_experience_block", lambda: "")
    monkeypatch.setattr(engine, "_save_user", lambda c: None)
    monkeypatch.setattr(engine, "_save_assistant", lambda m, c: None)
    monkeypatch.setattr(engine, "_reflect", lambda t, u: None)
    yield

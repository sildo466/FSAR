from __future__ import annotations

import importlib
import sqlite3
from types import SimpleNamespace

from src.memory import integrations
from src.server import integration_engine


def test_existing_models_table_gains_base_url_column():
    migration = importlib.import_module(
        "data.migrations.2026_07_16_pl2_6_integration_tables"
    )
    with sqlite3.connect(":memory:") as conn:
        conn.execute(
            "CREATE TABLE models ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, provider TEXT NOT NULL, "
            "model TEXT NOT NULL, persona_prompt TEXT NOT NULL, specialty TEXT DEFAULT '', "
            "temperature REAL DEFAULT 0.7, max_tokens INTEGER, "
            "created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )

        migration.up(conn)

        columns = {row[1] for row in conn.execute("PRAGMA table_info(models)")}
        assert "base_url" in columns


def test_model_base_url_round_trips(tmp_path, monkeypatch):
    monkeypatch.setattr(integrations, "_db_path", lambda: tmp_path / "memory.db")
    model_id = integrations.upsert_model(integrations.ModelSpec(
        provider="custom-relay",
        base_url="https://relay.example/v1",
        model="custom-model",
        persona_prompt="Answer directly.",
    ))

    saved = integrations.get_model(model_id)

    assert saved.provider == "custom-relay"
    assert saved.base_url == "https://relay.example/v1"
    assert saved.model == "custom-model"


def test_model_api_key_round_trips(tmp_path, monkeypatch):
    monkeypatch.setattr(integrations, "_db_path", lambda: tmp_path / "memory.db")
    model_id = integrations.upsert_model(integrations.ModelSpec(
        provider="custom-relay",
        api_key="sk-secret",
        model="custom-model",
        persona_prompt="Answer directly.",
    ))

    saved = integrations.get_model(model_id)

    assert saved.api_key == "sk-secret"


def test_integration_call_uses_model_base_url(monkeypatch):
    captured: dict[str, str] = {}
    client = object()

    def make_client(provider_id: str, base_url: str = "", api_key: str = ""):
        captured.update(provider_id=provider_id, base_url=base_url)
        return client

    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
        usage=SimpleNamespace(input_tokens=2, output_tokens=1),
    )
    monkeypatch.setattr(integration_engine, "_provider_id", lambda provider: provider)
    monkeypatch.setattr(integration_engine, "make_llm_client", make_client)
    monkeypatch.setattr(integration_engine, "cached_chat_completion", lambda *args, **kwargs: response)

    text, usage = integration_engine._call_provider(
        "custom-relay",
        "custom-model",
        [{"role": "user", "content": "hello"}],
        base_url="https://relay.example/v1",
    )

    assert captured == {
        "provider_id": "custom-relay",
        "base_url": "https://relay.example/v1",
    }
    assert text == "ok"
    assert usage == {"input_tokens": 2, "output_tokens": 1}


def test_call_provider_passes_protocol_override(monkeypatch):
    client = object()
    seen: dict[str, object] = {}

    def fake_completion(client_arg, **kwargs):
        seen.update(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        )

    monkeypatch.setattr(integration_engine, "_provider_id", lambda provider: provider)
    monkeypatch.setattr(integration_engine, "make_llm_client", lambda *a, **k: client)
    monkeypatch.setattr(integration_engine, "cached_chat_completion", fake_completion)

    integration_engine._call_provider(
        "relay", "responses-only-model",
        [{"role": "user", "content": "hi"}],
        protocol="responses",
    )
    assert seen.get("format_override") == "responses"

    seen.clear()
    integration_engine._call_provider(
        "relay", "responses-only-model",
        [{"role": "user", "content": "hi"}],
    )
    assert "format_override" not in seen

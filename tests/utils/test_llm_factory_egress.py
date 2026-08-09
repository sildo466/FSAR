from __future__ import annotations

from unittest.mock import MagicMock

from src.skills.egress import check_url
from src.utils import llm_factory
from src.utils.fsar_config import FsarConfig


def test_make_llm_client_allows_configured_custom_base_url(monkeypatch):
    class Config:
        def get_llm_config(self, provider_id):
            assert provider_id == "custom-relay"
            return {
                "api_key": "test-key",
                "base_url": "https://rare-relay.example/v1",
            }

        def get(self, path, default=None):
            values = {
                "security.egress.enabled": True,
                "security.egress.mode": "deny",
                "security.egress.allowlist": ["api.openai.com:443"],
                "security.egress.blocklist": [],
            }
            return values.get(path, default)

    config = Config()
    expected_client = object()
    monkeypatch.setattr(llm_factory, "get_config", lambda: config)
    monkeypatch.setattr(llm_factory, "OpenAI", MagicMock(return_value=expected_client))
    monkeypatch.setattr(llm_factory.httpx, "Client", lambda **kwargs: object())
    monkeypatch.setattr("src.skills.egress._resolve_addresses", lambda host, port: {"203.0.113.1"})
    llm_factory.reset_clients()

    try:
        assert not check_url("https://rare-relay.example/v1", config).allowed
        assert llm_factory.make_llm_client("custom-relay") is expected_client
    finally:
        llm_factory.reset_clients()


def test_make_llm_client_sees_provider_saved_after_first_load(tmp_path, monkeypatch):
    from src.utils import fsar_config as fsar_config_module
    from src.utils.config import get_config

    config = FsarConfig(tmp_path / "fsar.yaml")
    monkeypatch.setattr(fsar_config_module, "_default_instance", config)
    assert get_config() is config

    config.patch("llm.providers", [{
        "id": "new-provider",
        "api_key": "new-api-key",
        "base_url": "https://api.example.com/v1",
        "model": "model-a",
    }])
    expected_client = object()
    openai = MagicMock(return_value=expected_client)
    monkeypatch.setattr(llm_factory, "OpenAI", openai)
    monkeypatch.setattr(llm_factory.httpx, "Client", lambda **kwargs: object())
    llm_factory.reset_clients()

    try:
        assert llm_factory.make_llm_client("new-provider") is expected_client
        assert openai.call_args.kwargs["api_key"] == "new-api-key"
    finally:
        llm_factory.reset_clients()


def test_make_llm_client_uses_explicit_base_url_override(monkeypatch):
    class Config:
        def get_llm_config(self, provider_id):
            assert provider_id == "shared-credentials"
            return {
                "api_key": "test-key",
                "base_url": "https://default.example/v1",
            }

    openai = MagicMock(side_effect=lambda **kwargs: object())
    monkeypatch.setattr(llm_factory, "get_config", lambda: Config())
    monkeypatch.setattr(llm_factory, "OpenAI", openai)
    monkeypatch.setattr(llm_factory.httpx, "Client", lambda **kwargs: object())
    llm_factory.reset_clients()

    try:
        first = llm_factory.make_llm_client(
            "shared-credentials", base_url="https://integration.example/v1"
        )
        second = llm_factory.make_llm_client(
            "shared-credentials", base_url="https://integration.example/v1"
        )

        assert first is second
        assert openai.call_count == 1
        assert openai.call_args.kwargs["api_key"] == "test-key"
        assert openai.call_args.kwargs["base_url"] == "https://integration.example/v1"
    finally:
        llm_factory.reset_clients()


def test_make_llm_client_uses_explicit_api_key_override(monkeypatch):
    class Config:
        def get_llm_config(self, provider_id):
            return {
                "api_key": "provider-key",
                "base_url": "https://default.example/v1",
            }

    openai = MagicMock(side_effect=lambda **kwargs: object())
    monkeypatch.setattr(llm_factory, "get_config", lambda: Config())
    monkeypatch.setattr(llm_factory, "OpenAI", openai)
    monkeypatch.setattr(llm_factory.httpx, "Client", lambda **kwargs: object())
    llm_factory.reset_clients()

    try:
        client = llm_factory.make_llm_client(
            "shared-credentials",
            base_url="https://integration.example/v1",
            api_key="integration-key",
        )

        assert client is not None
        assert openai.call_args.kwargs["api_key"] == "integration-key"
    finally:
        llm_factory.reset_clients()

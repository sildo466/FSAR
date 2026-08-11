# SPDX-License-Identifier: Apache-2.0
"""Tests for the provider WS handler."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.server.handlers import provider as provider_handler
from src.utils.fsar_config import FsarConfig


@pytest.fixture
def fsar_config(tmp_path: Path) -> FsarConfig:
    cfg_path = tmp_path / "fsar.yaml"
    cfg_path.write_text(
        "onboarding:\n  completed: false\n  completed_steps: []\n"
        "llm:\n  active: null\n  providers: []\n",
        encoding="utf-8",
    )
    return FsarConfig(cfg_path)


def test_list_presets_returns_25(fsar_config):
    async def _run():
        return await provider_handler.provider_list_presets()

    result = asyncio.run(_run())
    assert result["type"] == "provider.presets"
    assert len(result["presets"]) == 25
    assert result["presets"][0]["id"] == "openai"


def test_create_builtin_writes_yaml(fsar_config, tmp_path: Path):
    async def _run():
        return await provider_handler.provider_create_builtin(
            fsar_config=fsar_config,
            preset_id="openai",
            label="OpenAI (primary)",
            api_key="${OPENAI_API_KEY}",
            base_url="https://api.openai.com/v1",
            model="gpt-4o-mini",
        )

    result = asyncio.run(_run())
    assert result["type"] == "provider.created"
    p = result["provider"]
    assert p["preset_id"] == "openai"
    assert p["model"] == "gpt-4o-mini"
    assert p["family"] == "openai_compat"
    assert "gpt-4o-mini" in (tmp_path / "fsar.yaml").read_text(encoding="utf-8")


def test_create_builtin_uses_preset_family(fsar_config):
    async def _run():
        return await provider_handler.provider_create_builtin(
            fsar_config=fsar_config,
            preset_id="anthropic",
            label="Anthropic",
            api_key="sk-test",
            base_url="https://api.anthropic.com/v1",
            model="claude-haiku-4-5-20251001",
        )

    result = asyncio.run(_run())
    p = result["provider"]
    assert p["family"] == "anthropic"


def test_create_builtin_is_idempotent_and_activates_reconfigured_model(fsar_config):
    async def _create(model: str):
        return await provider_handler.provider_create_builtin(
            fsar_config=fsar_config,
            preset_id="openai",
            label="OpenAI",
            api_key="sk-test",
            base_url="https://api.openai.com/v1",
            model=model,
        )

    first = asyncio.run(_create("gpt-4o-mini"))
    repeated = asyncio.run(_create("gpt-4o-mini"))
    reconfigured = asyncio.run(_create("gpt-4.1-mini"))

    providers = fsar_config.get("llm.providers")
    assert len(providers) == 1
    assert first["provider"]["id"] == repeated["provider"]["id"]
    assert providers[0]["model"] == "gpt-4.1-mini"
    assert fsar_config.get("llm.active") == reconfigured["provider"]["id"]


def test_create_builtin_unknown_preset_raises(fsar_config):
    async def _run():
        return await provider_handler.provider_create_builtin(
            fsar_config=fsar_config,
            preset_id="nonexistent",
            label="X",
            api_key="x",
            base_url="https://x.com/v1",
            model="x",
        )

    with pytest.raises(ValueError, match="preset not found"):
        asyncio.run(_run())


def test_test_connection_openai_compat_200():
    async def _run():
        fake_response = AsyncMock(status_code=200, json=lambda: {"data": [{"id": "x"}]})
        with patch("src.server.handlers.provider.httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = fake_response
            MockClient.return_value.__aenter__.return_value = mock_instance
            return await provider_handler.provider_test_connection(
                preset_id="openai",
                base_url="https://api.openai.com/v1",
                api_key="sk-test",
                model="gpt-4o-mini",
            )

    result = asyncio.run(_run())
    assert result["ok"] is True
    assert result["error"] is None


def test_test_connection_openai_compat_401():
    async def _run():
        fake_response = AsyncMock(status_code=401)
        with patch("src.server.handlers.provider.httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = fake_response
            MockClient.return_value.__aenter__.return_value = mock_instance
            return await provider_handler.provider_test_connection(
                preset_id="openai",
                base_url="https://api.openai.com/v1",
                api_key="sk-bad",
                model="gpt-4o-mini",
            )

    result = asyncio.run(_run())
    assert result["ok"] is False
    assert result["error"] == "auth_failed"


def test_test_connection_openai_compat_timeout():
    async def _run():
        with patch("src.server.handlers.provider.httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.get.side_effect = httpx.TimeoutException("timeout")
            MockClient.return_value.__aenter__.return_value = mock_instance
            return await provider_handler.provider_test_connection(
                preset_id="openai",
                base_url="https://api.openai.com/v1",
                api_key="sk-test",
                model="gpt-4o-mini",
            )

    result = asyncio.run(_run())
    assert result["ok"] is False
    assert result["error"] == "unreachable"


def test_test_connection_anthropic_uses_user_model():
    async def _run():
        fake_response = AsyncMock(status_code=200, json=lambda: {"content": []})
        with patch("src.server.handlers.provider.httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = fake_response
            MockClient.return_value.__aenter__.return_value = mock_instance
            return (
                await provider_handler.provider_test_connection(
                    preset_id="anthropic",
                    base_url="https://api.anthropic.com/v1",
                    api_key="sk-test",
                    model="claude-haiku-4-5-20251001",
                ),
                mock_instance,
            )

    result, mock_instance = asyncio.run(_run())
    assert result["ok"] is True
    call_args = mock_instance.post.call_args
    assert "claude-haiku-4-5-20251001" in str(call_args)


def test_test_connection_anthropic_model_required():
    async def _run():
        return await provider_handler.provider_test_connection(
            preset_id="anthropic",
            base_url="https://api.anthropic.com/v1",
            api_key="sk-test",
            model="",
        )

    result = asyncio.run(_run())
    assert result["ok"] is False
    assert result["error"] == "model_required"


def test_test_connection_anthropic_401():
    async def _run():
        fake_response = AsyncMock(status_code=401)
        with patch("src.server.handlers.provider.httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = fake_response
            MockClient.return_value.__aenter__.return_value = mock_instance
            return await provider_handler.provider_test_connection(
                preset_id="anthropic",
                base_url="https://api.anthropic.com/v1",
                api_key="sk-bad",
                model="claude-haiku-4-5-20251001",
            )

    result = asyncio.run(_run())
    assert result["ok"] is False
    assert result["error"] == "auth_failed"


def test_test_connection_google_200():
    async def _run():
        fake_response = AsyncMock(status_code=200, json=lambda: {"models": [{"name": "models/gemini-2.0-flash"}]})
        with patch("src.server.handlers.provider.httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = fake_response
            MockClient.return_value.__aenter__.return_value = mock_instance
            return await provider_handler.provider_test_connection(
                preset_id="google",
                base_url="https://generativelanguage.googleapis.com/v1beta",
                api_key="test-key",
                model="gemini-2.0-flash",
            )

    result = asyncio.run(_run())
    assert result["ok"] is True
    assert result["error"] is None


def test_test_connection_google_bad_key():
    async def _run():
        fake_response = AsyncMock(status_code=400)
        with patch("src.server.handlers.provider.httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = fake_response
            MockClient.return_value.__aenter__.return_value = mock_instance
            return await provider_handler.provider_test_connection(
                preset_id="google",
                base_url="https://generativelanguage.googleapis.com/v1beta",
                api_key="bad-key",
                model="gemini-2.0-flash",
            )

    result = asyncio.run(_run())
    assert result["ok"] is False
    assert result["error"] == "auth_failed"


def test_fetch_models_openai_compat():
    async def _run():
        fake_response = AsyncMock(status_code=200, json=lambda: {"data": [{"id": "gpt-4o-mini"}, {"id": "gpt-4o"}]})
        with patch("src.server.handlers.provider.httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = fake_response
            MockClient.return_value.__aenter__.return_value = mock_instance
            return await provider_handler.provider_fetch_models(
                preset_id="openai",
                base_url="https://api.openai.com/v1",
                api_key="sk-test",
            )

    result = asyncio.run(_run())
    assert result["ok"] is True
    assert "gpt-4o-mini" in result["models"]
    assert "gpt-4o" in result["models"]


def test_fetch_models_anthropic_empty():
    async def _run():
        return await provider_handler.provider_fetch_models(
            preset_id="anthropic",
            base_url="https://api.anthropic.com/v1",
            api_key="sk-test",
        )

    result = asyncio.run(_run())
    assert result["ok"] is False
    assert result["models"] == []


def test_dispatch_test_connection_sends_response(fsar_config):
    from fastapi import WebSocket

    async def _run():
        ws = AsyncMock()
        ws.send_json = AsyncMock()
        fake_response = AsyncMock(status_code=200, json=lambda: {"data": [{"id": "x"}]})
        with patch("src.server.handlers.provider.httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = fake_response
            MockClient.return_value.__aenter__.return_value = mock_instance
            handled = await provider_handler.dispatch(
                ws,
                {
                    "type": "provider.test_connection",
                    "preset_id": "openai",
                    "base_url": "https://api.openai.com/v1",
                    "api_key": "sk-test",
                    "model": "gpt-4o-mini",
                },
                fsar_config,
            )
        return handled, ws

    handled, ws = asyncio.run(_run())
    assert handled is True
    sent = ws.send_json.await_args.args[0]
    assert sent["type"] == "provider.test_result"
    assert sent["ok"] is True

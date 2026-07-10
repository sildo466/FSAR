# SPDX-License-Identifier: Apache-2.0
"""Tests for the provider WS handler."""
from __future__ import annotations

import asyncio
from pathlib import Path

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

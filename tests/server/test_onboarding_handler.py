# SPDX-License-Identifier: Apache-2.0
"""Tests for the onboarding WS handler."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from src.server.handlers import onboarding as onboarding_handler
from src.utils.fsar_config import FsarConfig

ALL_STEPS = ["provider", "embedding", "character_card", "user_card"]


@pytest.fixture
def fsar_config(tmp_path: Path) -> FsarConfig:
    cfg_path = tmp_path / "fsar.yaml"
    cfg_path.write_text(
        "onboarding:\n  completed: false\n  completed_steps: []\n"
        "llm:\n  active: null\n  providers: []\n",
        encoding="utf-8",
    )
    return FsarConfig(cfg_path)


def test_get_state_required_when_completed_false(fsar_config):
    async def _run():
        return await onboarding_handler.onboarding_get_state(fsar_config)

    result = asyncio.run(_run())
    assert result["type"] == "onboarding.state"
    assert result["required"] is True
    assert result["completed"] is False
    assert result["completed_steps"] == []
    assert result["current_step"] == "provider"


def test_get_state_not_required_when_completed_true(fsar_config):
    fsar_config.patch("onboarding.completed", True)
    fsar_config.patch("onboarding.completed_steps", ALL_STEPS)
    fsar_config.save()
    cfg = FsarConfig(fsar_config._path)
    async def _run():
        return await onboarding_handler.onboarding_get_state(cfg)

    result = asyncio.run(_run())
    assert result["required"] is False
    assert result["completed"] is True
    assert result["current_step"] is None


def test_get_state_resumes_from_completed_steps(fsar_config):
    fsar_config.patch("onboarding.completed_steps", ["provider"])
    fsar_config.save()
    cfg = FsarConfig(fsar_config._path)
    async def _run():
        return await onboarding_handler.onboarding_get_state(cfg)

    result = asyncio.run(_run())
    assert result["required"] is True
    assert result["current_step"] == "embedding"


def test_complete_step_appends_to_completed_steps(fsar_config, tmp_path: Path):
    async def _run():
        return await onboarding_handler.onboarding_complete_step(
            fsar_config=fsar_config,
            step="provider",
            data={"preset_id": "openai"},
        )

    result = asyncio.run(_run())
    assert result["type"] == "onboarding.step_completed"
    cfg = FsarConfig(fsar_config._path)
    assert cfg.get("onboarding.completed_steps") == ["provider"]
    assert "started_at" in cfg.get("onboarding", {})
    assert cfg.get("onboarding.last_step") == "provider"


def test_complete_step_rejects_unknown_step(fsar_config):
    async def _run():
        return await onboarding_handler.onboarding_complete_step(
            fsar_config=fsar_config,
            step="bogus",
            data={},
        )

    with pytest.raises(ValueError, match="unknown step"):
        asyncio.run(_run())


def test_complete_sets_completed_true(fsar_config, tmp_path: Path):
    async def _run():
        for s in ALL_STEPS:
            await onboarding_handler.onboarding_complete_step(
                fsar_config=fsar_config, step=s, data={},
            )
        cfg = FsarConfig(fsar_config._path)
        return await onboarding_handler.onboarding_complete(cfg)

    result = asyncio.run(_run())
    assert result["type"] == "onboarding.completed"
    assert result["redirect"] == "/chat"
    cfg2 = FsarConfig(fsar_config._path)
    assert cfg2.get("onboarding.completed") is True
    assert cfg2.get("onboarding.completed_at") is not None


def test_complete_requires_all_required_steps(fsar_config):
    async def _run():
        await onboarding_handler.onboarding_complete_step(
            fsar_config=fsar_config, step="provider", data={},
        )
        cfg = FsarConfig(fsar_config._path)
        await onboarding_handler.onboarding_complete(cfg)

    with pytest.raises(ValueError, match="incomplete"):
        asyncio.run(_run())


def test_reset_clears_completed(fsar_config, tmp_path: Path):
    async def _run():
        for s in ALL_STEPS:
            await onboarding_handler.onboarding_complete_step(
                fsar_config=fsar_config, step=s, data={},
            )
        cfg = FsarConfig(fsar_config._path)
        await onboarding_handler.onboarding_complete(cfg)
        cfg2 = FsarConfig(fsar_config._path)
        return await onboarding_handler.onboarding_reset(cfg2)

    result = asyncio.run(_run())
    assert result["required"] is True
    assert result["completed_steps"] == []
    cfg3 = FsarConfig(fsar_config._path)
    assert cfg3.get("onboarding.completed") is False
    assert cfg3.get("onboarding.completed_steps") == []

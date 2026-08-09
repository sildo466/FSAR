# SPDX-License-Identifier: MIT
"""Optional speech onboarding step tests."""

from unittest.mock import AsyncMock

import pytest

from src.server.handlers import onboarding
from src.utils.fsar_config import FsarConfig


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
@pytest.mark.parametrize("step", ["tts", "asr"])
async def test_skip_step_does_not_mark_step_completed(tmp_path, step):
    config = FsarConfig(tmp_path / "config.yaml")
    config.patch("onboarding.completed_steps", ["provider"])
    websocket = AsyncMock()
    await onboarding.dispatch(
        websocket,
        {"type": "onboarding.skip_step", "step": step},
        config,
    )
    assert step not in config.get("onboarding.completed_steps")
    assert websocket.send_json.call_args.args[0] == {
        "type": "onboarding.step_skipped",
        "step": step,
    }


@pytest.mark.anyio
async def test_complete_does_not_require_optional_speech_steps(tmp_path):
    config = FsarConfig(tmp_path / "config.yaml")
    config.patch(
        "onboarding.completed_steps",
        ["provider", "character_card", "user_card"],
    )
    result = await onboarding.onboarding_complete(config)
    assert result["type"] == "onboarding.completed"

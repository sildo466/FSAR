# SPDX-License-Identifier: MIT
"""Speech configuration validation tests."""

from unittest.mock import AsyncMock

import pytest

from src.server.handlers import settings
from src.utils.fsar_config import FsarConfig


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_speech_patch_accepts_provider_and_active_id(tmp_path):
    config = FsarConfig(tmp_path / "config.yaml")
    websocket = AsyncMock()
    providers = [{"id": "p1", "preset_id": "openai", "voice": "alloy"}]
    await settings.dispatch(
        websocket,
        {
            "type": "settings.patch",
            "patch": {
                "tts.providers": providers,
                "tts.active": "p1",
                "tts.autoplay": True,
                "asr.language": "zh",
            },
        },
        config,
    )
    assert config.get("tts.active") == "p1"
    assert config.get("tts.autoplay") is True
    assert config.get("asr.language") == "zh"


@pytest.mark.anyio
async def test_speech_patch_rejects_unknown_active_id(tmp_path):
    config = FsarConfig(tmp_path / "config.yaml")
    config.patch("tts.providers", [])
    websocket = AsyncMock()
    await settings.dispatch(
        websocket,
        {"type": "settings.patch", "patch": {"tts.active": "missing"}},
        config,
    )
    sent = websocket.send_json.call_args.args[0]
    assert sent["type"] == "error"
    assert sent["code"] == "bad_speech_setting"
    assert config.get("tts.active") is None


@pytest.mark.anyio
async def test_speech_patch_rejects_wrong_type(tmp_path):
    config = FsarConfig(tmp_path / "config.yaml")
    websocket = AsyncMock()
    await settings.dispatch(
        websocket,
        {"type": "settings.patch", "patch": {"tts.autoplay": "yes"}},
        config,
    )
    assert websocket.send_json.call_args.args[0]["code"] == "bad_speech_setting"


@pytest.mark.anyio
async def test_unknown_speech_path_is_ignored(tmp_path):
    config = FsarConfig(tmp_path / "config.yaml")
    websocket = AsyncMock()
    await settings.dispatch(
        websocket,
        {"type": "settings.patch", "patch": {"tts.unplanned": "value"}},
        config,
    )
    assert config.get("tts.unplanned") is None
    assert websocket.send_json.call_args.args[0]["patch"] == {}

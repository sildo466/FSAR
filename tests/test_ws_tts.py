# SPDX-License-Identifier: MIT
"""TTS WebSocket handler tests."""

import base64
from unittest.mock import AsyncMock

import pytest

from src.providers.tts.adapters.base import TtsError
from src.server.handlers import tts as tts_handler
from src.utils.fsar_config import FsarConfig


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def config(tmp_path):
    result = FsarConfig(tmp_path / "config.yaml")
    result.patch("tts.active", "p1")
    result.patch(
        "tts.providers",
        [{"id": "p1", "family": "openai_compat", "voice": "alloy"}],
    )
    return result


@pytest.mark.anyio
async def test_synthesize_returns_audio_frame(config, monkeypatch):
    websocket = AsyncMock()
    monkeypatch.setattr(
        tts_handler, "tts_synthesize", AsyncMock(return_value=b"MP3")
    )
    handled = await tts_handler.dispatch(
        websocket,
        {"type": "tts.synthesize", "request_id": "r1", "text": "hi"},
        config,
    )
    assert handled is True
    sent = websocket.send_json.call_args.args[0]
    assert sent["type"] == "tts.audio"
    assert sent["request_id"] == "r1"
    assert base64.b64decode(sent["audio"]) == b"MP3"


@pytest.mark.anyio
async def test_synthesize_returns_stable_error(config, monkeypatch):
    websocket = AsyncMock()
    monkeypatch.setattr(
        tts_handler,
        "tts_synthesize",
        AsyncMock(side_effect=TtsError("no_voice", "voice required")),
    )
    await tts_handler.dispatch(
        websocket,
        {"type": "tts.synthesize", "request_id": "r1", "text": "hi"},
        config,
    )
    sent = websocket.send_json.call_args.args[0]
    assert sent["type"] == "tts.error"
    assert sent["code"] == "no_voice"


@pytest.mark.anyio
async def test_voices_returns_adapter_catalog(config, monkeypatch):
    websocket = AsyncMock()
    adapter = AsyncMock()
    adapter.list_voices.return_value = ["alloy"]
    monkeypatch.setattr(tts_handler, "get_adapter", lambda family: adapter)
    await tts_handler.dispatch(
        websocket,
        {"type": "tts.voices", "request_id": "r2", "provider_id": "p1"},
        config,
    )
    sent = websocket.send_json.call_args.args[0]
    assert sent == {
        "type": "tts.voices_result",
        "request_id": "r2",
        "voices": ["alloy"],
    }


@pytest.mark.anyio
async def test_synthesize_passes_instructions_override(config, monkeypatch):
    websocket = AsyncMock()
    synth = AsyncMock(return_value=b"MP3")
    monkeypatch.setattr(tts_handler, "tts_synthesize", synth)
    await tts_handler.dispatch(
        websocket,
        {
            "type": "tts.synthesize",
            "request_id": "r1",
            "text": "hi",
            "instructions_override": "cheerful",
        },
        config,
    )
    assert synth.call_args.kwargs["character_instructions_override"] == "cheerful"


@pytest.mark.anyio
async def test_synthesize_reports_wav_mime(config, monkeypatch):
    websocket = AsyncMock()
    monkeypatch.setattr(
        tts_handler, "tts_synthesize", AsyncMock(return_value=b"RIFF$\x00WAVE")
    )
    await tts_handler.dispatch(
        websocket,
        {"type": "tts.synthesize", "request_id": "r1", "text": "hi"},
        config,
    )
    sent = websocket.send_json.call_args.args[0]
    assert sent["mime"] == "audio/wav"

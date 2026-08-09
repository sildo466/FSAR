# SPDX-License-Identifier: MIT
"""ASR WebSocket handler tests."""

import base64
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.server.handlers import asr as asr_handler
from src.utils.fsar_config import FsarConfig


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def config(tmp_path):
    result = FsarConfig(tmp_path / "config.yaml")
    result.patch("asr.active", "p1")
    result.patch("asr.providers", [{"id": "p1", "family": "openai_compat"}])
    return result


@pytest.mark.anyio
async def test_transcribe_returns_text(config, monkeypatch):
    websocket = AsyncMock()
    monkeypatch.setattr(
        asr_handler, "asr_transcribe", AsyncMock(return_value="hello world")
    )
    handled = await asr_handler.dispatch(
        websocket,
        {
            "type": "asr.transcribe",
            "request_id": "a1",
            "audio": base64.b64encode(b"audio").decode("ascii"),
            "mime_type": "audio/webm",
        },
        config,
    )
    assert handled is True
    sent = websocket.send_json.call_args.args[0]
    assert sent["type"] == "asr.text"
    assert sent["text"] == "hello world"


@pytest.mark.anyio
async def test_bad_base64_returns_error(config):
    websocket = AsyncMock()
    await asr_handler.dispatch(
        websocket,
        {"type": "asr.transcribe", "request_id": "a1", "audio": "%%%"},
        config,
    )
    sent = websocket.send_json.call_args.args[0]
    assert sent["type"] == "asr.error"
    assert sent["code"] == "bad_audio"


@pytest.mark.anyio
async def test_model_list_returns_catalog(config, monkeypatch):
    websocket = AsyncMock()
    model_api = MagicMock()
    model_api.MODEL_SIZES = {"base": 150_000_000}
    model_api.list_downloaded.return_value = ["base"]
    monkeypatch.setattr(asr_handler, "faster_whisper_models", model_api)
    await asr_handler.dispatch(websocket, {"type": "asr.model_list"}, config)
    sent = websocket.send_json.call_args.args[0]
    assert sent["type"] == "asr.model_list_result"
    assert sent["downloaded"] == ["base"]


@pytest.mark.anyio
async def test_model_download_emits_lifecycle(config, monkeypatch):
    websocket = AsyncMock()
    model_api = MagicMock()
    model_api.MODEL_SIZES = {"base": 150_000_000}
    model_api.ModelDownloadError = RuntimeError
    model_api.resolve_hf_endpoint.return_value = SimpleNamespace(
        url="https://hf-mirror.com", source="mirror"
    )

    def download(size, progress, endpoint=None):
        progress(75_000_000, 150_000_000)
        return str(Path("cache") / size)

    model_api.download.side_effect = download
    monkeypatch.setattr(asr_handler, "faster_whisper_models", model_api)
    await asr_handler.dispatch(
        websocket,
        {"type": "asr.model_download", "request_id": "a2", "size": "base"},
        config,
    )
    frames = [call.args[0]["type"] for call in websocket.send_json.call_args_list]
    assert frames[0] == "asr.model_download_started"
    assert "asr.model_download_progress" in frames
    assert frames[-1] == "asr.model_download_done"
    started_payload = websocket.send_json.call_args_list[0].args[0]
    assert started_payload["endpoint"] == "https://hf-mirror.com"
    assert started_payload["endpoint_source"] == "mirror"


@pytest.mark.anyio
async def test_model_delete_returns_result(config, monkeypatch):
    websocket = AsyncMock()
    model_api = MagicMock()
    model_api.delete.return_value = True
    monkeypatch.setattr(asr_handler, "faster_whisper_models", model_api)
    await asr_handler.dispatch(
        websocket,
        {"type": "asr.model_delete", "request_id": "a3", "size": "base"},
        config,
    )
    sent = websocket.send_json.call_args.args[0]
    assert sent["type"] == "asr.model_deleted"
    assert sent["ok"] is True

# SPDX-License-Identifier: MIT
"""ASR adapter and dispatcher tests."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.providers.asr import dispatch
from src.providers.asr.adapters.base import AsrError
from src.providers.asr.adapters.openai_compat import OpenAICompatAsrAdapter
from src.providers.asr.adapters.volcengine import VolcengineAsrAdapter
from src.utils.fsar_config import FsarConfig


@pytest.fixture
def anyio_backend():
    return "asyncio"


def response(status=200, json_data=None):
    result = MagicMock(status_code=status, text="upstream error")
    result.json.return_value = json_data or {}
    return result


def client(mock, result):
    instance = AsyncMock()
    instance.post.return_value = result
    instance.__aenter__.return_value = instance
    instance.__aexit__.return_value = False
    mock.return_value = instance
    return instance


@pytest.mark.anyio
async def test_openai_compat_transcribe_sends_multipart():
    with patch("src.providers.asr.adapters.openai_compat.httpx.AsyncClient") as mock:
        instance = client(mock, response(json_data={"text": "hello world"}))
        result = await OpenAICompatAsrAdapter().transcribe(
            audio=b"audio",
            mime_type="audio/webm",
            language="auto",
            model="whisper-1",
            api_key="sk",
            base_url="https://api.openai.com/v1",
        )
    assert result == "hello world"
    call = instance.post.call_args
    assert call.args[0] == "https://api.openai.com/v1/audio/transcriptions"
    assert call.kwargs["files"]["file"][0] == "audio.webm"
    assert "language" not in call.kwargs["data"]


@pytest.mark.anyio
async def test_openai_compat_requires_model():
    with pytest.raises(AsrError) as caught:
        await OpenAICompatAsrAdapter().transcribe(
            audio=b"audio",
            mime_type="audio/webm",
            language="auto",
            model="",
            api_key="sk",
            base_url="https://api.openai.com/v1",
        )
    assert caught.value.code == "no_model"


@pytest.mark.anyio
async def test_volcengine_uses_semicolon_bearer():
    with patch("src.providers.asr.adapters.volcengine.httpx.AsyncClient") as mock:
        instance = client(mock, response(json_data={"text": "ni hao"}))
        result = await VolcengineAsrAdapter().transcribe(
            audio=b"audio",
            mime_type="audio/wav",
            language="auto",
            model="",
            api_key="token",
            base_url="https://volcengine.example/asr",
        )
    assert result == "ni hao"
    assert instance.post.call_args.kwargs["headers"]["Authorization"] == "Bearer; token"


@pytest.mark.anyio
async def test_dispatch_no_active_provider(tmp_path):
    config = FsarConfig(tmp_path / "config.yaml")
    with pytest.raises(AsrError) as caught:
        await dispatch.asr_transcribe(
            config=config,
            audio=b"audio",
            mime_type="audio/webm",
        )
    assert caught.value.code == "no_asr_active"


@pytest.mark.anyio
async def test_dispatch_routes_local_provider(tmp_path, monkeypatch):
    config = FsarConfig(tmp_path / "config.yaml")
    config.patch("asr.active", "local")
    config.patch(
        "asr.providers",
        [{"id": "local", "family": "local", "model": "base", "language": "auto"}],
    )
    transcribe = AsyncMock(return_value="hello")
    monkeypatch.setattr(
        "src.providers.asr.adapters.faster_whisper.transcribe", transcribe
    )
    result = await dispatch.asr_transcribe(
        config=config,
        audio=b"audio",
        mime_type="audio/webm",
    )
    assert result == "hello"
    transcribe.assert_awaited_once()

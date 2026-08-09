# SPDX-License-Identifier: MIT
"""TTS adapter contract and request translation tests."""

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.providers.tts.adapters.base import TtsError
from src.providers.tts.adapters.openai_compat import OpenAICompatAdapter


@pytest.fixture
def anyio_backend():
    return "asyncio"


def response(status: int = 200, *, content: bytes = b"audio", json_data=None):
    result = MagicMock(status_code=status, content=content, text="upstream error")
    if json_data is not None:
        result.json.return_value = json_data
    return result


def async_client(mock_client, *, post=None, get=None):
    client = AsyncMock()
    if post is not None:
        client.post.return_value = post
    if get is not None:
        client.get.return_value = get
    client.__aenter__.return_value = client
    client.__aexit__.return_value = False
    mock_client.return_value = client
    return client


@pytest.mark.anyio
async def test_openai_compat_synthesize_returns_audio_bytes():
    with patch("src.providers.tts.adapters.openai_compat.httpx.AsyncClient") as mock:
        client = async_client(mock, post=response(content=b"MP3"))
        result = await OpenAICompatAdapter().synthesize(
            text="hello",
            voice="alloy",
            model="tts-1",
            api_key="sk-test",
            base_url="https://api.openai.com/v1",
        )
    assert result == b"MP3"
    call = client.post.call_args
    assert call.args[0] == "https://api.openai.com/v1/audio/speech"
    assert call.kwargs["json"] == {
        "model": "tts-1",
        "input": "hello",
        "voice": "alloy",
        "response_format": "mp3",
    }
    assert call.kwargs["headers"]["Authorization"] == "Bearer sk-test"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("voice", "model", "code"),
    [("", "tts-1", "no_voice"), ("alloy", "", "no_model")],
)
async def test_openai_compat_requires_voice_and_model(voice, model, code):
    with pytest.raises(TtsError) as caught:
        await OpenAICompatAdapter().synthesize(
            text="hello",
            voice=voice,
            model=model,
            api_key="sk",
            base_url="https://api.openai.com/v1",
        )
    assert caught.value.code == code


@pytest.mark.anyio
async def test_openai_compat_maps_upstream_status():
    with patch("src.providers.tts.adapters.openai_compat.httpx.AsyncClient") as mock:
        async_client(mock, post=response(status=401))
        with pytest.raises(TtsError) as caught:
            await OpenAICompatAdapter().synthesize(
                text="hello",
                voice="alloy",
                model="tts-1",
                api_key="bad",
                base_url="https://api.openai.com/v1",
            )
    assert caught.value.code == "provider_4xx"
    assert caught.value.http_status == 401


@pytest.mark.anyio
async def test_openai_compat_maps_timeout():
    with patch("src.providers.tts.adapters.openai_compat.httpx.AsyncClient") as mock:
        client = async_client(mock)
        client.post.side_effect = httpx.ReadTimeout("slow")
        with pytest.raises(TtsError) as caught:
            await OpenAICompatAdapter().synthesize(
                text="hello",
                voice="alloy",
                model="tts-1",
                api_key="sk",
                base_url="https://api.openai.com/v1",
            )
    assert caught.value.code == "timeout"


@pytest.mark.anyio
async def test_edge_synthesize_collects_audio(monkeypatch):
    from src.providers.tts.adapters import edge

    communicate = MagicMock()

    async def stream():
        yield {"type": "audio", "data": b"A"}
        yield {"type": "WordBoundary", "offset": 1}
        yield {"type": "audio", "data": b"B"}

    communicate.stream = stream
    edge_tts = MagicMock()
    edge_tts.Communicate.return_value = communicate
    monkeypatch.setattr(edge, "_load_edge_tts", lambda: edge_tts)
    result = await edge.EdgeAdapter().synthesize(
        text="hi", voice="en-US-Ava", model="", api_key="", base_url=""
    )
    assert result == b"AB"


@pytest.mark.anyio
async def test_elevenlabs_sends_voice_in_path():
    from src.providers.tts.adapters.elevenlabs import ElevenLabsAdapter

    with patch("src.providers.tts.adapters.elevenlabs.httpx.AsyncClient") as mock:
        client = async_client(mock, post=response(content=b"MP3"))
        result = await ElevenLabsAdapter().synthesize(
            text="hi",
            voice="abc123",
            model="eleven_multilingual_v2",
            api_key="sk",
            base_url="https://api.elevenlabs.io/v1",
        )
    assert result == b"MP3"
    call = client.post.call_args
    assert call.args[0].endswith("/text-to-speech/abc123")
    assert call.kwargs["headers"]["xi-api-key"] == "sk"


@pytest.mark.anyio
async def test_azure_sends_escaped_ssml():
    from src.providers.tts.adapters.azure import AzureAdapter

    with patch("src.providers.tts.adapters.azure.httpx.AsyncClient") as mock:
        client = async_client(mock, post=response(content=b"MP3"))
        result = await AzureAdapter().synthesize(
            text="one < two",
            voice="en-US-Ava",
            model="",
            api_key="subkey",
            base_url="https://eastasia.tts.speech.microsoft.com/cognitiveservices/v1",
        )
    assert result == b"MP3"
    call = client.post.call_args
    assert "one &lt; two" in call.kwargs["content"]
    assert call.kwargs["headers"]["Ocp-Apim-Subscription-Key"] == "subkey"


@pytest.mark.anyio
async def test_dashscope_fetches_signed_audio_url():
    from src.providers.tts.adapters.dashscope import DashScopeAdapter

    created = response(json_data={"output": {"audio": {"url": "https://signed/audio"}}})
    with patch("src.providers.tts.adapters.dashscope.httpx.AsyncClient") as mock:
        client = async_client(mock, post=created, get=response(content=b"MP3"))
        result = await DashScopeAdapter().synthesize(
            text="hi",
            voice="longxiaochun",
            model="cosyvoice-v2",
            api_key="sk",
            base_url="https://dashscope.example/tts",
        )
    assert result == b"MP3"
    client.get.assert_awaited_once_with("https://signed/audio")


@pytest.mark.anyio
async def test_volcengine_uses_semicolon_bearer():
    from src.providers.tts.adapters.volcengine import VolcengineAdapter

    encoded = base64.b64encode(b"MP3").decode("ascii")
    with patch("src.providers.tts.adapters.volcengine.httpx.AsyncClient") as mock:
        client = async_client(mock, post=response(json_data={"data": encoded}))
        result = await VolcengineAdapter().synthesize(
            text="hi",
            voice="BV001_streaming",
            model="",
            api_key="token",
            base_url="https://volcengine.example/tts",
            extra={"appid": "app123"},
        )
    assert result == b"MP3"
    assert client.post.call_args.kwargs["headers"]["Authorization"] == "Bearer; token"


@pytest.mark.anyio
async def test_minimax_sync_post_returns_hex_decoded_audio():
    from src.providers.tts.adapters.minimax import MiniMaxAdapter

    audio_hex = b"MP3".hex()
    with patch("src.providers.tts.adapters.minimax.httpx.AsyncClient") as mock:
        client = async_client(
            mock, post=response(json_data={"data": {"audio": audio_hex}})
        )
        result = await MiniMaxAdapter().synthesize(
            text="hi",
            voice="male-qn-qingse",
            model="speech-2.8-hd",
            api_key="token",
            base_url="https://api.minimaxi.com/v1",
        )
    assert result == b"MP3"
    call = client.post.call_args
    assert call.args[0] == "https://api.minimaxi.com/v1/t2a_v2"
    assert call.kwargs["json"]["stream"] is False
    assert call.kwargs["json"]["voice_setting"]["voice_id"] == "male-qn-qingse"
    assert call.kwargs["headers"]["Authorization"] == "Bearer token"
    assert client.get.await_count == 0


@pytest.mark.anyio
async def test_minimax_sync_maps_upstream_status():
    from src.providers.tts.adapters.minimax import MiniMaxAdapter

    with patch("src.providers.tts.adapters.minimax.httpx.AsyncClient") as mock:
        async_client(mock, post=response(status=401))
        with pytest.raises(TtsError) as caught:
            await MiniMaxAdapter().synthesize(
                text="hi",
                voice="male-qn-qingse",
                model="speech-2.8-hd",
                api_key="bad",
                base_url="https://api.minimaxi.com/v1",
            )
    assert caught.value.code == "provider_4xx"
    assert caught.value.http_status == 401


@pytest.mark.anyio
async def test_minimax_sync_maps_timeout():
    from src.providers.tts.adapters.minimax import MiniMaxAdapter

    with patch("src.providers.tts.adapters.minimax.httpx.AsyncClient") as mock:
        client = async_client(mock)
        client.post.side_effect = httpx.ReadTimeout("slow")
        with pytest.raises(TtsError) as caught:
            await MiniMaxAdapter().synthesize(
                text="hi",
                voice="male-qn-qingse",
                model="speech-2.8-hd",
                api_key="token",
                base_url="https://api.minimaxi.com/v1",
            )
    assert caught.value.code == "timeout"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("voice", "model", "code"),
    [("", "speech-2.8-hd", "no_voice"), ("male-qn-qingse", "", "no_model")],
)
async def test_minimax_requires_voice_and_model(voice, model, code):
    from src.providers.tts.adapters.minimax import MiniMaxAdapter

    with pytest.raises(TtsError) as caught:
        await MiniMaxAdapter().synthesize(
            text="hi",
            voice=voice,
            model=model,
            api_key="token",
            base_url="https://api.minimaxi.com/v1",
        )
    assert caught.value.code == code


@pytest.mark.anyio
async def test_all_adapters_return_empty_voice_catalog():
    from src.providers.tts.adapters import get_adapter

    for family in (
        "edge",
        "openai_compat",
        "elevenlabs",
        "azure",
        "dashscope",
        "volcengine",
        "minimax",
    ):
        assert await get_adapter(family).list_voices(api_key="", base_url="") == []


def test_detect_audio_mime_identifies_wav():
    from src.providers.tts.adapters.base import detect_audio_mime

    assert detect_audio_mime(b"RIFF$\x00\x00\x00WAVEfmt ") == "audio/wav"


def test_detect_audio_mime_identifies_mp3():
    from src.providers.tts.adapters.base import detect_audio_mime

    assert detect_audio_mime(b"ID3\x04\x00") == "audio/mpeg"
    assert detect_audio_mime(b"\xff\xfb\x90\x00") == "audio/mpeg"


def test_detect_audio_mime_falls_back_to_mpeg():
    from src.providers.tts.adapters.base import detect_audio_mime

    assert detect_audio_mime(b"") == "audio/mpeg"
    assert detect_audio_mime(b"????") == "audio/mpeg"


@pytest.mark.anyio
async def test_dashscope_qwen_posts_multimodal_generation_body():
    from src.providers.tts.adapters.dashscope import DashScopeAdapter

    created = response(
        json_data={"output": {"audio": {"url": "https://signed/audio.wav"}}}
    )
    with patch("src.providers.tts.adapters.dashscope.httpx.AsyncClient") as mock:
        client = async_client(mock, post=created, get=response(content=b"WAV"))
        result = await DashScopeAdapter().synthesize(
            text="hi",
            voice="Cherry",
            model="qwen3-tts-flash",
            api_key="sk",
            base_url="https://dashscope.example/generation",
        )
    assert result == b"WAV"
    call = client.post.call_args
    assert call.args[0] == "https://dashscope.example/generation"
    assert call.kwargs["json"] == {
        "model": "qwen3-tts-flash",
        "input": {"text": "hi", "voice": "Cherry"},
    }
    client.get.assert_awaited_once_with("https://signed/audio.wav")


@pytest.mark.anyio
async def test_dashscope_qwen_instruct_includes_instructions():
    from src.providers.tts.adapters.dashscope import DashScopeAdapter

    created = response(
        json_data={"output": {"audio": {"url": "https://signed/audio.wav"}}}
    )
    with patch("src.providers.tts.adapters.dashscope.httpx.AsyncClient") as mock:
        client = async_client(mock, post=created, get=response(content=b"WAV"))
        await DashScopeAdapter().synthesize(
            text="hi",
            voice="Cherry",
            model="qwen3-tts-instruct-flash",
            api_key="sk",
            base_url="https://dashscope.example/generation",
            extra={"instructions": "speak cheerfully"},
        )
    assert client.post.call_args.kwargs["json"]["input"]["instructions"] == (
        "speak cheerfully"
    )


@pytest.mark.anyio
async def test_dashscope_qwen_drops_instructions_for_non_instruct_model():
    from src.providers.tts.adapters.dashscope import DashScopeAdapter

    created = response(
        json_data={"output": {"audio": {"url": "https://signed/audio.wav"}}}
    )
    with patch("src.providers.tts.adapters.dashscope.httpx.AsyncClient") as mock:
        client = async_client(mock, post=created, get=response(content=b"WAV"))
        await DashScopeAdapter().synthesize(
            text="hi",
            voice="Cherry",
            model="qwen3-tts-flash",
            api_key="sk",
            base_url="https://dashscope.example/generation",
            extra={"instructions": "speak cheerfully"},
        )
    assert "instructions" not in client.post.call_args.kwargs["json"]["input"]


@pytest.mark.anyio
async def test_dashscope_legacy_body_unchanged_for_cosyvoice():
    from src.providers.tts.adapters.dashscope import DashScopeAdapter

    created = response(
        json_data={"output": {"audio": {"url": "https://signed/audio"}}}
    )
    with patch("src.providers.tts.adapters.dashscope.httpx.AsyncClient") as mock:
        client = async_client(mock, post=created, get=response(content=b"MP3"))
        await DashScopeAdapter().synthesize(
            text="hi",
            voice="longxiaochun",
            model="cosyvoice-v2",
            api_key="sk",
            base_url="https://dashscope.example/tts",
        )
    assert client.post.call_args.kwargs["json"] == {
        "model": "cosyvoice-v2",
        "input": {"text": "hi"},
        "parameters": {"voice": "longxiaochun", "audio": {"format": "mp3"}},
    }

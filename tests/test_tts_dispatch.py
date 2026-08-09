# SPDX-License-Identifier: MIT
"""TTS dispatcher tests."""

from unittest.mock import AsyncMock

import pytest

from src.providers.tts import dispatch
from src.providers.tts.adapters.base import TtsError
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
        [
            {
                "id": "p1",
                "preset_id": "openai",
                "family": "openai_compat",
                "label": "OpenAI",
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-test",
                "voice": "alloy",
                "model": "tts-1",
                "enabled": True,
            }
        ],
    )
    return result


@pytest.mark.anyio
async def test_no_active_provider_raises(tmp_path):
    config = FsarConfig(tmp_path / "config.yaml")
    config.patch("tts.active", "")
    config.patch("tts.providers", [])
    with pytest.raises(TtsError) as caught:
        await dispatch.tts_synthesize(config=config, text="hi")
    assert caught.value.code == "no_tts_active"


@pytest.mark.anyio
async def test_no_voice_raises(config):
    config.patch("tts.providers", [{**config.get("tts.providers")[0], "voice": ""}])
    with pytest.raises(TtsError) as caught:
        await dispatch.tts_synthesize(config=config, text="hi")
    assert caught.value.code == "no_voice"


@pytest.mark.anyio
async def test_cache_miss_calls_adapter(config, monkeypatch):
    monkeypatch.setattr(dispatch.tts_cache, "l1_get", lambda key: None)
    monkeypatch.setattr(dispatch.tts_cache, "l2_get", lambda key: None)
    monkeypatch.setattr(dispatch.tts_cache, "l1_put", lambda *args: None)
    monkeypatch.setattr(dispatch.tts_cache, "l2_put", lambda *args: None)
    adapter = AsyncMock()
    adapter.synthesize.return_value = b"MP3"
    monkeypatch.setattr(dispatch, "get_adapter", lambda family: adapter)
    result = await dispatch.tts_synthesize(config=config, text="hello")
    assert result == b"MP3"
    assert adapter.synthesize.call_args.kwargs["voice"] == "alloy"
    assert adapter.synthesize.call_args.kwargs["model"] == "tts-1"


@pytest.mark.anyio
async def test_l1_cache_hit_skips_adapter(config, monkeypatch):
    monkeypatch.setattr(dispatch.tts_cache, "l1_get", lambda key: b"CACHED")
    adapter = AsyncMock()
    monkeypatch.setattr(dispatch, "get_adapter", lambda family: adapter)
    assert await dispatch.tts_synthesize(config=config, text="hello") == b"CACHED"
    adapter.synthesize.assert_not_awaited()


@pytest.mark.anyio
async def test_character_voice_override(config, monkeypatch):
    monkeypatch.setattr(dispatch.tts_cache, "l1_get", lambda key: None)
    monkeypatch.setattr(dispatch.tts_cache, "l2_get", lambda key: None)
    monkeypatch.setattr(dispatch.tts_cache, "l1_put", lambda *args: None)
    monkeypatch.setattr(dispatch.tts_cache, "l2_put", lambda *args: None)
    adapter = AsyncMock()
    adapter.synthesize.return_value = b"MP3"
    monkeypatch.setattr(dispatch, "get_adapter", lambda family: adapter)
    await dispatch.tts_synthesize(
        config=config,
        text="hello",
        character_voice_override="echo",
    )
    assert adapter.synthesize.call_args.kwargs["voice"] == "echo"


@pytest.mark.anyio
@pytest.mark.parametrize("change", ["long", "extra", "bypass"])
async def test_cache_bypass_conditions(config, monkeypatch, change):
    reads = []
    monkeypatch.setattr(
        dispatch.tts_cache, "l1_get", lambda key: reads.append(key) or None
    )
    monkeypatch.setattr(dispatch.tts_cache, "l1_put", lambda *args: None)
    monkeypatch.setattr(dispatch.tts_cache, "l2_put", lambda *args: None)
    adapter = AsyncMock()
    adapter.synthesize.return_value = b"MP3"
    monkeypatch.setattr(dispatch, "get_adapter", lambda family: adapter)
    kwargs = {}
    text = "x" * 1001 if change == "long" else "hello"
    if change == "extra":
        provider = {**config.get("tts.providers")[0], "extra": {"rate": 10}}
        config.patch("tts.providers", [provider])
    if change == "bypass":
        kwargs["bypass_cache"] = True
    await dispatch.tts_synthesize(config=config, text=text, **kwargs)
    assert reads == []


@pytest.mark.anyio
async def test_retry_once_on_429(config, monkeypatch):
    monkeypatch.setattr(dispatch.tts_cache, "l1_get", lambda key: None)
    monkeypatch.setattr(dispatch.tts_cache, "l2_get", lambda key: None)
    monkeypatch.setattr(dispatch.tts_cache, "l1_put", lambda *args: None)
    monkeypatch.setattr(dispatch.tts_cache, "l2_put", lambda *args: None)
    monkeypatch.setattr(dispatch.asyncio, "sleep", AsyncMock())
    adapter = AsyncMock()
    adapter.synthesize.side_effect = [
        TtsError("provider_4xx", "rate limited", http_status=429),
        b"MP3",
    ]
    monkeypatch.setattr(dispatch, "get_adapter", lambda family: adapter)
    assert await dispatch.tts_synthesize(config=config, text="hello") == b"MP3"
    assert adapter.synthesize.await_count == 2


@pytest.mark.anyio
async def test_edge_does_not_require_model(config, monkeypatch):
    provider = {
        **config.get("tts.providers")[0],
        "preset_id": "edge",
        "family": "edge",
        "model": "",
    }
    config.patch("tts.providers", [provider])
    monkeypatch.setattr(dispatch.tts_cache, "l1_get", lambda key: None)
    monkeypatch.setattr(dispatch.tts_cache, "l2_get", lambda key: None)
    monkeypatch.setattr(dispatch.tts_cache, "l1_put", lambda *args: None)
    monkeypatch.setattr(dispatch.tts_cache, "l2_put", lambda *args: None)
    adapter = AsyncMock()
    adapter.synthesize.return_value = b"MP3"
    monkeypatch.setattr(dispatch, "get_adapter", lambda family: adapter)
    assert await dispatch.tts_synthesize(config=config, text="hello") == b"MP3"


@pytest.mark.anyio
async def test_character_instructions_override_reaches_adapter_and_cache_key(
    config, monkeypatch
):
    reads = []
    monkeypatch.setattr(
        dispatch.tts_cache, "l1_get", lambda key: reads.append(key) or None
    )
    monkeypatch.setattr(dispatch.tts_cache, "l2_get", lambda key: None)
    monkeypatch.setattr(dispatch.tts_cache, "l1_put", lambda *args: None)
    monkeypatch.setattr(dispatch.tts_cache, "l2_put", lambda *args: None)
    adapter = AsyncMock()
    adapter.synthesize.return_value = b"MP3"
    monkeypatch.setattr(dispatch, "get_adapter", lambda family: adapter)
    await dispatch.tts_synthesize(
        config=config,
        text="hello",
        character_instructions_override="cheerful",
    )
    assert adapter.synthesize.call_args.kwargs["extra"]["instructions"] == "cheerful"
    plain_key = dispatch.tts_cache.tts_cache_key("p1", "alloy", "tts-1", "hello")
    assert reads[0] != plain_key


@pytest.mark.anyio
async def test_provider_extra_instructions_used_when_no_override(config, monkeypatch):
    provider = {
        **config.get("tts.providers")[0],
        "extra": {"instructions": "gentle"},
    }
    config.patch("tts.providers", [provider])
    monkeypatch.setattr(dispatch.tts_cache, "l1_get", lambda key: None)
    monkeypatch.setattr(dispatch.tts_cache, "l2_get", lambda key: None)
    monkeypatch.setattr(dispatch.tts_cache, "l1_put", lambda *args: None)
    monkeypatch.setattr(dispatch.tts_cache, "l2_put", lambda *args: None)
    adapter = AsyncMock()
    adapter.synthesize.return_value = b"MP3"
    monkeypatch.setattr(dispatch, "get_adapter", lambda family: adapter)
    await dispatch.tts_synthesize(config=config, text="hello")
    assert adapter.synthesize.call_args.kwargs["extra"]["instructions"] == "gentle"


@pytest.mark.anyio
async def test_character_override_beats_provider_extra(config, monkeypatch):
    provider = {
        **config.get("tts.providers")[0],
        "extra": {"instructions": "gentle"},
    }
    config.patch("tts.providers", [provider])
    monkeypatch.setattr(dispatch.tts_cache, "l1_get", lambda key: None)
    monkeypatch.setattr(dispatch.tts_cache, "l2_get", lambda key: None)
    monkeypatch.setattr(dispatch.tts_cache, "l1_put", lambda *args: None)
    monkeypatch.setattr(dispatch.tts_cache, "l2_put", lambda *args: None)
    adapter = AsyncMock()
    adapter.synthesize.return_value = b"MP3"
    monkeypatch.setattr(dispatch, "get_adapter", lambda family: adapter)
    await dispatch.tts_synthesize(
        config=config,
        text="hello",
        character_instructions_override="cheerful",
    )
    assert adapter.synthesize.call_args.kwargs["extra"]["instructions"] == "cheerful"


@pytest.mark.anyio
async def test_instructions_only_extra_stays_cacheable(config, monkeypatch):
    provider = {
        **config.get("tts.providers")[0],
        "extra": {"instructions": "gentle"},
    }
    config.patch("tts.providers", [provider])
    reads = []
    monkeypatch.setattr(
        dispatch.tts_cache, "l1_get", lambda key: reads.append(key) or None
    )
    monkeypatch.setattr(dispatch.tts_cache, "l2_get", lambda key: None)
    monkeypatch.setattr(dispatch.tts_cache, "l1_put", lambda *args: None)
    monkeypatch.setattr(dispatch.tts_cache, "l2_put", lambda *args: None)
    adapter = AsyncMock()
    adapter.synthesize.return_value = b"MP3"
    monkeypatch.setattr(dispatch, "get_adapter", lambda family: adapter)
    await dispatch.tts_synthesize(config=config, text="hello")
    assert len(reads) == 1


@pytest.mark.anyio
async def test_cache_put_uses_sniffed_mime(config, monkeypatch):
    monkeypatch.setattr(dispatch.tts_cache, "l1_get", lambda key: None)
    monkeypatch.setattr(dispatch.tts_cache, "l2_get", lambda key: None)
    puts = []
    monkeypatch.setattr(
        dispatch.tts_cache,
        "l1_put",
        lambda key, audio, mime="audio/mpeg": puts.append(mime),
    )
    monkeypatch.setattr(dispatch.tts_cache, "l2_put", lambda *args: None)
    adapter = AsyncMock()
    adapter.synthesize.return_value = b"RIFF$\x00WAVEfmt "
    monkeypatch.setattr(dispatch, "get_adapter", lambda family: adapter)
    await dispatch.tts_synthesize(config=config, text="hello")
    assert puts == ["audio/wav"]

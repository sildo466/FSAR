# SPDX-License-Identifier: MIT
"""TTS provider selection, caching, and retry dispatch."""

from __future__ import annotations

import asyncio
from pathlib import Path

from src.utils.fsar_config import FsarConfig

from . import cache as tts_cache
from .adapters import get_adapter
from .adapters.base import TtsError, detect_audio_mime
from .presets import get_preset_by_id, load_presets

_PRESET_PATH = Path(__file__).resolve().parents[3] / "data" / "presets" / "tts-providers.json"


def _provider_family(provider: dict) -> str:
    family = str(provider.get("family") or "").strip()
    if family:
        return family
    try:
        preset = get_preset_by_id(
            load_presets(_PRESET_PATH), str(provider.get("preset_id") or "")
        )
    except (OSError, ValueError):
        preset = None
    return str((preset or {}).get("family") or "openai_compat")


async def tts_synthesize(
    *,
    config: FsarConfig,
    text: str,
    character_voice_override: str = "",
    character_instructions_override: str = "",
    bypass_cache: bool = False,
) -> bytes:
    active_id = str(config.get("tts.active") or "")
    if not active_id:
        raise TtsError("no_tts_active", "no TTS provider is active")
    providers = config.get("tts.providers") or []
    provider = next(
        (
            item
            for item in providers
            if isinstance(item, dict)
            and item.get("id") == active_id
            and item.get("enabled", True) is not False
        ),
        None,
    )
    if provider is None:
        raise TtsError(
            "no_tts_active",
            f"active provider {active_id!r} is unavailable",
        )
    voice = str(
        character_voice_override
        or provider.get("voice")
        or config.get("tts.default_voice")
        or ""
    ).strip()
    if not voice:
        raise TtsError("no_voice", f"provider {active_id!r} has no voice configured")
    model = str(provider.get("model") or "").strip()
    family = _provider_family(provider)
    extra_value = provider.get("extra")
    extra = extra_value if isinstance(extra_value, dict) else None
    instructions = str(
        character_instructions_override or (extra or {}).get("instructions") or ""
    ).strip()
    adapter_extra = (
        {**(extra or {}), "instructions": instructions} if instructions else extra
    )
    non_instructions_extra = {
        k: v for k, v in (extra or {}).items() if k != "instructions"
    }
    cacheable = len(text) <= 1000 and not non_instructions_extra
    key = tts_cache.tts_cache_key(active_id, voice, model, text, instructions)

    if cacheable and not bypass_cache:
        try:
            audio = tts_cache.l1_get(key)
            if audio is not None:
                return audio
            stored = tts_cache.l2_get(key)
            if stored is not None:
                audio, mime = stored
                tts_cache.l1_put(key, audio, mime)
                return audio
        except Exception:
            pass

    try:
        adapter = get_adapter(family)
    except KeyError as error:
        raise TtsError("provider_4xx", str(error)) from error
    audio = await _synthesize_with_retry(
        adapter,
        text=text,
        voice=voice,
        model=model,
        api_key=str(provider.get("api_key") or ""),
        base_url=str(provider.get("base_url") or ""),
        extra=adapter_extra,
    )
    if cacheable and audio:
        try:
            mime = detect_audio_mime(audio)
            tts_cache.l1_put(key, audio, mime)
            tts_cache.l2_put(
                key,
                audio,
                mime,
                active_id,
                voice,
                model,
                len(text),
            )
        except Exception:
            pass
    return audio


async def _synthesize_with_retry(
    adapter,
    *,
    text: str,
    voice: str,
    model: str,
    api_key: str,
    base_url: str,
    extra: dict | None,
) -> bytes:
    for attempt in range(2):
        try:
            return await adapter.synthesize(
                text=text,
                voice=voice,
                model=model,
                api_key=api_key,
                base_url=base_url,
                extra=extra,
            )
        except TtsError as error:
            status = error.http_status
            retryable = status == 429 or bool(status and 500 <= status < 600)
            if retryable and attempt == 0:
                await asyncio.sleep(1.0)
                continue
            if status == 429:
                raise TtsError(
                    "provider_5xx",
                    str(error),
                    http_status=status,
                ) from error
            raise
    raise RuntimeError("unreachable")

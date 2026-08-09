# SPDX-License-Identifier: MIT
"""ASR provider selection and dispatch."""

from __future__ import annotations

from pathlib import Path

from src.utils.fsar_config import FsarConfig

from .adapters import get_adapter
from .adapters.base import AsrError
from .presets import get_preset_by_id, load_presets

_PRESET_PATH = Path(__file__).resolve().parents[3] / "data" / "presets" / "asr-providers.json"


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


async def asr_transcribe(
    *,
    config: FsarConfig,
    audio: bytes,
    mime_type: str,
) -> str:
    if not audio:
        raise AsrError("bad_audio", "audio is empty")
    active_id = str(config.get("asr.active") or "")
    if not active_id:
        raise AsrError("no_asr_active", "no ASR provider is active")
    providers = config.get("asr.providers") or []
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
        raise AsrError(
            "no_asr_active", f"active provider {active_id!r} is unavailable"
        )
    family = _provider_family(provider)
    model = str(provider.get("model") or "").strip()
    language = str(
        provider.get("language") or config.get("asr.language") or "auto"
    ).strip()
    if family == "local":
        from .adapters.faster_whisper import transcribe

        return await transcribe(
            audio=audio,
            mime_type=mime_type,
            language=language,
            model=model,
        )
    try:
        adapter = get_adapter(family)
    except KeyError as error:
        raise AsrError("provider_4xx", str(error)) from error
    return await adapter.transcribe(
        audio=audio,
        mime_type=mime_type,
        language=language,
        model=model,
        api_key=str(provider.get("api_key") or ""),
        base_url=str(provider.get("base_url") or ""),
    )

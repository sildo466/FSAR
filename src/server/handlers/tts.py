# SPDX-License-Identifier: MIT
"""WebSocket dispatcher for TTS messages."""

from __future__ import annotations

import base64
from typing import Any

from fastapi import WebSocket

from src.providers.tts.adapters import get_adapter
from src.providers.tts.adapters.base import TtsError, detect_audio_mime
from src.providers.tts.dispatch import tts_synthesize
from src.utils.fsar_config import FsarConfig


async def dispatch(
    ws: WebSocket,
    msg: dict[str, Any],
    config: FsarConfig,
) -> bool:
    message_type = msg.get("type")
    if message_type == "tts.synthesize":
        return await _handle_synthesize(ws, msg, config)
    if message_type == "tts.voices":
        return await _handle_voices(ws, msg, config)
    return False


async def _handle_synthesize(
    ws: WebSocket,
    msg: dict[str, Any],
    config: FsarConfig,
) -> bool:
    request_id = str(msg.get("request_id") or "")
    try:
        audio = await tts_synthesize(
            config=config,
            text=str(msg.get("text") or ""),
            character_voice_override=str(msg.get("voice_override") or ""),
            character_instructions_override=str(msg.get("instructions_override") or ""),
            bypass_cache=bool(msg.get("bypass_cache", False)),
        )
    except TtsError as error:
        payload: dict[str, Any] = {
            "type": "tts.error",
            "request_id": request_id,
            "code": error.code,
            "message": str(error),
        }
        if error.http_status is not None:
            payload["http_status"] = error.http_status
        await ws.send_json(payload)
        return True
    await ws.send_json(
        {
            "type": "tts.audio",
            "request_id": request_id,
            "mime": detect_audio_mime(audio),
            "audio": base64.b64encode(audio).decode("ascii"),
        }
    )
    return True


async def _handle_voices(
    ws: WebSocket,
    msg: dict[str, Any],
    config: FsarConfig,
) -> bool:
    request_id = str(msg.get("request_id") or "")
    provider_id = str(msg.get("provider_id") or "")
    providers = config.get("tts.providers") or []
    provider = next(
        (
            item
            for item in providers
            if isinstance(item, dict) and item.get("id") == provider_id
        ),
        None,
    )
    voices: list[str] = []
    if provider is not None:
        try:
            adapter = get_adapter(str(provider.get("family") or "openai_compat"))
            voices = await adapter.list_voices(
                api_key=str(provider.get("api_key") or ""),
                base_url=str(provider.get("base_url") or ""),
            )
        except (KeyError, TtsError):
            voices = []
    await ws.send_json(
        {
            "type": "tts.voices_result",
            "request_id": request_id,
            "voices": voices,
        }
    )
    return True

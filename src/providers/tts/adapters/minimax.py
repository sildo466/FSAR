# SPDX-License-Identifier: MIT
"""MiniMax synchronous text-to-speech adapter."""

from __future__ import annotations

import httpx

from .base import TtsError, transport_error, upstream_error


class MiniMaxAdapter:
    id = "minimax"
    family = "minimax"

    async def list_voices(self, *, api_key: str, base_url: str) -> list[str]:
        return []

    async def synthesize(
        self,
        *,
        text: str,
        voice: str,
        model: str,
        api_key: str,
        base_url: str,
        extra: dict | None = None,
    ) -> bytes:
        if not voice:
            raise TtsError("no_voice", "voice id is required for MiniMax TTS")
        if not model:
            raise TtsError("no_model", "model is required for MiniMax TTS")
        options = extra or {}
        body = {
            "model": model,
            "text": text,
            "stream": False,
            "voice_setting": {
                "voice_id": voice,
                "speed": options.get("speed", 1.0),
                "vol": options.get("vol", 1.0),
                "pitch": options.get("pitch", 0),
            },
            "audio_setting": {
                "sample_rate": options.get("sample_rate", 32000),
                "bitrate": options.get("bitrate", 128000),
                "format": options.get("audio_format", "mp3"),
                "channel": 1,
            },
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        url = f"{base_url.rstrip('/')}/t2a_v2"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=body, headers=headers)
        except httpx.HTTPError as error:
            raise transport_error(error) from error
        if response.status_code >= 400:
            raise upstream_error(response, prefix="minimax")
        try:
            data = response.json()
            hex_audio = data["data"]["audio"]
        except (KeyError, TypeError, ValueError) as error:
            raise TtsError(
                "provider_5xx", f"MiniMax response missing audio: {error}"
            ) from error
        try:
            return bytes.fromhex(hex_audio)
        except ValueError as error:
            raise TtsError(
                "provider_5xx", f"MiniMax audio payload is not valid hex: {error}"
            ) from error
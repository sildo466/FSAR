# SPDX-License-Identifier: MIT
"""ElevenLabs text-to-speech adapter."""

from __future__ import annotations

from urllib.parse import quote

import httpx

from .base import TtsError, transport_error, upstream_error


class ElevenLabsAdapter:
    id = "elevenlabs"
    family = "elevenlabs"

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
            raise TtsError("no_voice", "voice id is required for ElevenLabs")
        if not model:
            raise TtsError("no_model", "model is required for ElevenLabs")
        body: dict = {"text": text, "model_id": model}
        if (extra or {}).get("voice_settings"):
            body["voice_settings"] = extra["voice_settings"]
        headers = {
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{base_url.rstrip('/')}/text-to-speech/{quote(voice, safe='')}",
                    json=body,
                    headers=headers,
                )
        except httpx.HTTPError as error:
            raise transport_error(error) from error
        if response.status_code >= 400:
            raise upstream_error(response)
        return response.content

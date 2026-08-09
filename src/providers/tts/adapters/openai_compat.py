# SPDX-License-Identifier: MIT
"""OpenAI-compatible text-to-speech adapter."""

from __future__ import annotations

import httpx

from .base import TtsError, transport_error, upstream_error


class OpenAICompatAdapter:
    id = "openai_compat"
    family = "openai_compat"

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
            raise TtsError("no_voice", "voice is required")
        if not model:
            raise TtsError("no_model", "model is required")
        body = {
            "model": model,
            "input": text,
            "voice": voice,
            "response_format": (extra or {}).get("response_format", "mp3"),
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{base_url.rstrip('/')}/audio/speech",
                    json=body,
                    headers=headers,
                )
        except httpx.HTTPError as error:
            raise transport_error(error) from error
        if response.status_code >= 400:
            raise upstream_error(response)
        return response.content

# SPDX-License-Identifier: MIT
"""Microsoft Azure Speech text-to-speech adapter."""

from __future__ import annotations

from xml.sax.saxutils import escape, quoteattr

import httpx

from .base import TtsError, transport_error, upstream_error


def _build_ssml(text: str, voice: str, rate: str, pitch: str) -> str:
    return (
        "<speak version='1.0' xml:lang='en-US'>"
        f"<voice name={quoteattr(voice)}>"
        f"<prosody rate={quoteattr(rate)} pitch={quoteattr(pitch)}>"
        f"{escape(text)}</prosody></voice></speak>"
    )


class AzureAdapter:
    id = "azure"
    family = "azure"

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
            raise TtsError("no_voice", "voice is required for Azure Speech")
        options = extra or {}
        output_format = options.get(
            "output_format", "audio-24khz-48kbitrate-mono-mp3"
        )
        headers = {
            "Ocp-Apim-Subscription-Key": api_key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": output_format,
        }
        ssml = _build_ssml(
            text,
            voice,
            str(options.get("rate_str", "+0%")),
            str(options.get("pitch_str", "+0%")),
        )
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(base_url.rstrip("/"), content=ssml, headers=headers)
        except httpx.HTTPError as error:
            raise transport_error(error) from error
        if response.status_code >= 400:
            raise upstream_error(response)
        return response.content

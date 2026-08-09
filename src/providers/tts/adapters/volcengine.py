# SPDX-License-Identifier: MIT
"""Volcengine text-to-speech adapter."""

from __future__ import annotations

import base64
import uuid

import httpx

from .base import TtsError, transport_error, upstream_error


class VolcengineAdapter:
    id = "volcengine"
    family = "volcengine"

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
            raise TtsError("no_voice", "voice is required for Volcengine TTS")
        options = extra or {}
        appid = str(options.get("appid", ""))
        if not appid:
            raise TtsError("provider_4xx", "Volcengine appid is required in extra")
        body = {
            "app": {
                "appid": appid,
                "cluster": options.get("cluster", "volcano_tts"),
            },
            "user": {"uid": "fsar-server"},
            "audio": {
                "voice": voice,
                "format": options.get("audio_format", "mp3"),
                "speed_ratio": options.get("speed", 1.0),
            },
            "request": {
                "reqid": str(uuid.uuid4()),
                "text": text,
                "operation": "query",
            },
        }
        headers = {
            "Authorization": f"Bearer; {api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(base_url, json=body, headers=headers)
        except httpx.HTTPError as error:
            raise transport_error(error) from error
        if response.status_code >= 400:
            raise upstream_error(response)
        try:
            return base64.b64decode(response.json()["data"], validate=True)
        except (KeyError, TypeError, ValueError) as error:
            raise TtsError(
                "provider_5xx",
                f"Volcengine response missing valid audio data: {error}",
            ) from error

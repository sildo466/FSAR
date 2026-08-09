# SPDX-License-Identifier: MIT
"""OpenAI-compatible audio transcription adapter."""

from __future__ import annotations

import httpx

from .base import AsrError, transport_error, upstream_error


def _extension_for(mime_type: str) -> str:
    return {
        "audio/webm": "webm",
        "audio/ogg": "ogg",
        "audio/mp4": "mp4",
        "audio/m4a": "m4a",
        "audio/wav": "wav",
        "audio/x-wav": "wav",
        "audio/mpeg": "mp3",
        "audio/mp3": "mp3",
    }.get(mime_type.lower(), "bin")


class OpenAICompatAsrAdapter:
    id = "openai_compat"
    family = "openai_compat"

    async def transcribe(
        self,
        *,
        audio: bytes,
        mime_type: str,
        language: str,
        model: str,
        api_key: str,
        base_url: str,
    ) -> str:
        if not model:
            raise AsrError("no_model", "model is required")
        files = {
            "file": (
                f"audio.{_extension_for(mime_type)}",
                audio,
                mime_type,
            )
        }
        data = {"model": model, "response_format": "json"}
        if language and language != "auto":
            data["language"] = language
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{base_url.rstrip('/')}/audio/transcriptions",
                    files=files,
                    data=data,
                    headers={"Authorization": f"Bearer {api_key}"},
                )
        except httpx.HTTPError as error:
            raise transport_error(error) from error
        if response.status_code >= 400:
            raise upstream_error(response)
        try:
            return str(response.json().get("text", "")).strip()
        except (AttributeError, TypeError, ValueError) as error:
            raise AsrError(
                "provider_5xx", f"upstream response parse failed: {error}"
            ) from error

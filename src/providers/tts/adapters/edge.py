# SPDX-License-Identifier: MIT
"""Microsoft Edge text-to-speech adapter."""

from __future__ import annotations

import io

from .base import TtsError


def _load_edge_tts():
    try:
        import edge_tts
    except ImportError as error:
        raise TtsError("provider_5xx", "edge-tts is not installed") from error
    return edge_tts


class EdgeAdapter:
    id = "edge"
    family = "edge"

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
            raise TtsError("no_voice", "voice is required for edge-tts")
        rate = int((extra or {}).get("rate", 0))
        rate_text = f"{rate:+d}%"
        try:
            communicate = _load_edge_tts().Communicate(
                text=text,
                voice=voice,
                rate=rate_text,
            )
            buffer = io.BytesIO()
            async for chunk in communicate.stream():
                if chunk.get("type") == "audio":
                    buffer.write(chunk.get("data", b""))
        except TtsError:
            raise
        except Exception as error:
            raise TtsError("provider_5xx", f"edge-tts failed: {error}") from error
        audio = buffer.getvalue()
        if not audio:
            raise TtsError("provider_5xx", "edge-tts returned no audio")
        return audio

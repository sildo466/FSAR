# SPDX-License-Identifier: MIT
"""TTS adapter contract and shared error translation."""

from __future__ import annotations

from typing import Protocol

import httpx


class TtsError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        http_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.http_status = http_status


class TtsAdapter(Protocol):
    id: str
    family: str

    async def list_voices(self, *, api_key: str, base_url: str) -> list[str]: ...

    async def synthesize(
        self,
        *,
        text: str,
        voice: str,
        model: str,
        api_key: str,
        base_url: str,
        extra: dict | None = None,
    ) -> bytes: ...


def upstream_error(response: httpx.Response, *, prefix: str = "upstream") -> TtsError:
    code = "provider_4xx" if response.status_code < 500 else "provider_5xx"
    snippet = response.text[:256] if response.text else ""
    return TtsError(
        code,
        f"{prefix} {response.status_code}: {snippet}",
        http_status=response.status_code,
    )


def transport_error(error: httpx.HTTPError) -> TtsError:
    if isinstance(error, httpx.TimeoutException):
        return TtsError("timeout", str(error))
    if isinstance(error, httpx.ConnectError):
        return TtsError("connection_refused", str(error))
    return TtsError("provider_5xx", str(error))


def detect_audio_mime(audio: bytes) -> str:
    if audio[:4] == b"RIFF":
        return "audio/wav"
    if audio[:3] == b"ID3" or audio[:1] == b"\xff":
        return "audio/mpeg"
    return "audio/mpeg"

# SPDX-License-Identifier: MIT
"""ASR adapter contract and shared error translation."""

from __future__ import annotations

from typing import Protocol

import httpx


class AsrError(Exception):
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


class AsrAdapter(Protocol):
    id: str
    family: str

    async def transcribe(
        self,
        *,
        audio: bytes,
        mime_type: str,
        language: str,
        model: str,
        api_key: str,
        base_url: str,
    ) -> str: ...


def upstream_error(response: httpx.Response) -> AsrError:
    code = "provider_4xx" if response.status_code < 500 else "provider_5xx"
    snippet = response.text[:256] if response.text else ""
    return AsrError(
        code,
        f"upstream {response.status_code}: {snippet}",
        http_status=response.status_code,
    )


def transport_error(error: httpx.HTTPError) -> AsrError:
    if isinstance(error, httpx.TimeoutException):
        return AsrError("timeout", str(error))
    if isinstance(error, httpx.ConnectError):
        return AsrError("connection_refused", str(error))
    return AsrError("provider_5xx", str(error))

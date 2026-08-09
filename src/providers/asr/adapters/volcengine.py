# SPDX-License-Identifier: MIT
"""Volcengine non-streaming audio transcription adapter."""

from __future__ import annotations

import base64
import uuid

import httpx

from .base import AsrError, transport_error, upstream_error


class VolcengineAsrAdapter:
    id = "volcengine"
    family = "volcengine"

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
        body = {
            "app": {"appid": "", "cluster": "volcengine_input_file"},
            "user": {"uid": "fsar-server"},
            "audio": {
                "format": mime_type.split("/", 1)[-1],
                "data": base64.b64encode(audio).decode("ascii"),
            },
            "request": {
                "reqid": str(uuid.uuid4()),
                "sequence": -1,
                "operation": "submit",
            },
        }
        headers = {
            "Authorization": f"Bearer; {api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(base_url, json=body, headers=headers)
        except httpx.HTTPError as error:
            raise transport_error(error) from error
        if response.status_code >= 400:
            raise upstream_error(response)
        try:
            data = response.json()
        except ValueError as error:
            raise AsrError("provider_5xx", f"invalid Volcengine response: {error}") from error
        if "text" in data:
            return str(data["text"]).strip()
        result = data.get("result")
        if isinstance(result, list) and result and isinstance(result[0], dict):
            return str(result[0].get("text", "")).strip()
        raise AsrError("provider_5xx", f"unrecognized Volcengine response: {data}")

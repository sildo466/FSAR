# SPDX-License-Identifier: MIT
"""Alibaba DashScope CosyVoice text-to-speech adapter."""

from __future__ import annotations

import httpx

from .base import TtsError, transport_error, upstream_error


class DashScopeAdapter:
    id = "dashscope"
    family = "dashscope"

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
            raise TtsError("no_voice", "voice is required for DashScope")
        if not model:
            raise TtsError("no_model", "model is required for DashScope")
        if model.strip().lower().startswith("qwen"):
            body = self._qwen_body(text=text, voice=voice, model=model, extra=extra)
        else:
            body = {
                "model": model,
                "input": {"text": text},
                "parameters": {
                    "voice": voice,
                    "audio": {"format": (extra or {}).get("audio_format", "mp3")},
                },
            }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(base_url, json=body, headers=headers)
                if response.status_code >= 400:
                    raise upstream_error(response)
                try:
                    signed_url = response.json()["output"]["audio"]["url"]
                except (KeyError, TypeError, ValueError) as error:
                    raise TtsError(
                        "provider_5xx",
                        f"DashScope response missing audio URL: {error}",
                    ) from error
                audio_response = await client.get(signed_url)
        except TtsError:
            raise
        except httpx.HTTPError as error:
            raise transport_error(error) from error
        if audio_response.status_code >= 400:
            raise upstream_error(audio_response, prefix="DashScope audio fetch")
        return audio_response.content

    @staticmethod
    def _qwen_body(
        *,
        text: str,
        voice: str,
        model: str,
        extra: dict | None,
    ) -> dict:
        input_payload: dict = {"text": text, "voice": voice}
        instructions = str((extra or {}).get("instructions") or "").strip()
        if instructions and "instruct" in model.lower():
            input_payload["instructions"] = instructions
        return {"model": model, "input": input_payload}

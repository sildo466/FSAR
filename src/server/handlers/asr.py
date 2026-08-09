# SPDX-License-Identifier: MIT
"""WebSocket dispatcher for ASR and local model management."""

from __future__ import annotations

import asyncio
import base64
import binascii
from typing import Any

from fastapi import WebSocket

from src.providers.asr.adapters import faster_whisper_models
from src.providers.asr.adapters.base import AsrError
from src.providers.asr.dispatch import asr_transcribe
from src.utils.fsar_config import FsarConfig


async def dispatch(
    ws: WebSocket,
    msg: dict[str, Any],
    config: FsarConfig,
) -> bool:
    message_type = msg.get("type")
    if message_type == "asr.transcribe":
        return await _handle_transcribe(ws, msg, config)
    if message_type == "asr.model_list":
        return await _handle_model_list(ws, msg)
    if message_type == "asr.model_download":
        return await _handle_model_download(ws, msg)
    if message_type == "asr.model_delete":
        return await _handle_model_delete(ws, msg)
    return False


async def _handle_transcribe(
    ws: WebSocket,
    msg: dict[str, Any],
    config: FsarConfig,
) -> bool:
    request_id = str(msg.get("request_id") or "")
    try:
        audio = base64.b64decode(str(msg.get("audio") or ""), validate=True)
        if not audio:
            raise ValueError("empty audio")
    except (binascii.Error, ValueError):
        await ws.send_json(
            {
                "type": "asr.error",
                "request_id": request_id,
                "code": "bad_audio",
                "message": "audio is not valid base64",
            }
        )
        return True
    try:
        text = await asr_transcribe(
            config=config,
            audio=audio,
            mime_type=str(msg.get("mime_type") or "audio/webm"),
        )
    except AsrError as error:
        payload: dict[str, Any] = {
            "type": "asr.error",
            "request_id": request_id,
            "code": error.code,
            "message": str(error),
        }
        if error.http_status is not None:
            payload["http_status"] = error.http_status
        await ws.send_json(payload)
        return True
    await ws.send_json(
        {
            "type": "asr.text",
            "request_id": request_id,
            "text": text,
            "language": str(config.get("asr.language") or "auto"),
        }
    )
    return True


async def _handle_model_list(ws: WebSocket, msg: dict[str, Any]) -> bool:
    await ws.send_json(
        {
            "type": "asr.model_list_result",
            "request_id": str(msg.get("request_id") or ""),
            "downloaded": faster_whisper_models.list_downloaded(),
            "available": list(faster_whisper_models.MODEL_SIZES),
            "sizes": faster_whisper_models.MODEL_SIZES,
        }
    )
    return True


async def _handle_model_download(ws: WebSocket, msg: dict[str, Any]) -> bool:
    request_id = str(msg.get("request_id") or "")
    size = str(msg.get("size") or "")
    if size not in faster_whisper_models.MODEL_SIZES:
        await ws.send_json(
            {
                "type": "asr.error",
                "request_id": request_id,
                "code": "bad_size",
                "message": f"unknown model size: {size}",
            }
        )
        return True
    total = faster_whisper_models.MODEL_SIZES[size]
    resolved = faster_whisper_models.resolve_hf_endpoint()
    await ws.send_json(
        {
            "type": "asr.model_download_started",
            "request_id": request_id,
            "size": size,
            "total_bytes": total,
            "endpoint": resolved.url,
            "endpoint_source": resolved.source,
        }
    )
    loop = asyncio.get_running_loop()
    updates: asyncio.Queue[tuple[int, int]] = asyncio.Queue()

    def progress(received: int, expected: int) -> None:
        loop.call_soon_threadsafe(updates.put_nowait, (received, expected))

    task = asyncio.create_task(
        asyncio.to_thread(
            faster_whisper_models.download, size, progress=progress, endpoint=resolved
        )
    )
    last_reported = 0
    try:
        while not task.done():
            try:
                received, expected = await asyncio.wait_for(updates.get(), timeout=1.0)
            except asyncio.TimeoutError:
                if task.done():
                    break
                disk_usage = faster_whisper_models.model_disk_usage_bytes(size)
                received = disk_usage if isinstance(disk_usage, int) else 0
                if received <= last_reported:
                    continue
                expected = total
            last_reported = max(last_reported, received)
            await _send_download_progress(
                ws, request_id, size, received, expected or total
            )
        path = await task
        while not updates.empty():
            received, expected = updates.get_nowait()
            await _send_download_progress(
                ws, request_id, size, received, expected or total
            )
        await ws.send_json(
            {
                "type": "asr.model_download_done",
                "request_id": request_id,
                "size": size,
                "path": path,
            }
        )
    except faster_whisper_models.ModelDownloadError as error:
        await ws.send_json(
            {
                "type": "asr.model_download_error",
                "request_id": request_id,
                "size": size,
                "code": error.code,
                "message": str(error),
            }
        )
    return True


async def _send_download_progress(
    ws: WebSocket,
    request_id: str,
    size: str,
    received: int,
    total: int,
) -> None:
    percent = min(100.0, received / total * 100) if total else 0.0
    await ws.send_json(
        {
            "type": "asr.model_download_progress",
            "request_id": request_id,
            "size": size,
            "received_bytes": received,
            "percent": round(percent, 1),
        }
    )


async def _handle_model_delete(ws: WebSocket, msg: dict[str, Any]) -> bool:
    size = str(msg.get("size") or "")
    await ws.send_json(
        {
            "type": "asr.model_deleted",
            "request_id": str(msg.get("request_id") or ""),
            "size": size,
            "ok": faster_whisper_models.delete(size),
        }
    )
    return True

# SPDX-License-Identifier: Apache-2.0
"""WS dispatcher for Settings + LLM provider selection."""

from __future__ import annotations

from typing import Any

from fastapi import WebSocket

from src.utils.fsar_config import FsarConfig


async def dispatch(ws: WebSocket, msg: dict[str, Any], config: FsarConfig) -> bool:
    t = msg.get("type")
    if t == "settings.get":
        await ws.send_json({"type": "snapshot", "config": config._settings})
        return True
    if t == "settings.patch":
        patch = msg.get("patch") or {}
        if not isinstance(patch, dict):
            await ws.send_json({"type": "error", "code": "bad_patch", "recoverable": True})
            return True
        for key, value in patch.items():
            if not isinstance(key, str) or not key:
                continue
            config.patch(key, value)
        try:
            config.save()
        except Exception:
            pass
        await ws.send_json({"type": "settings.changed", "patch": patch, "by": "user"})
        return True
    if t == "llm.set_active":
        provider_id = msg.get("provider_id", "")
        if not provider_id:
            await ws.send_json({"type": "error", "code": "no_provider_id", "recoverable": True})
            return True
        config.set_active_provider(provider_id)
        try:
            config.save()
        except Exception:
            pass
        active = config.get_active_provider()
        await ws.send_json({
            "type": "llm.provider_changed",
            "provider_id": provider_id,
            "model": active.get("model", ""),
        })
        return True
    return False

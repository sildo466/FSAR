# SPDX-License-Identifier: Apache-2.0
"""WS dispatcher for reflection controls."""

from __future__ import annotations

from typing import Any

from fastapi import WebSocket

from src.utils.fsar_config import FsarConfig

VALID_INTENSITY = {"off", "low", "medium", "high"}


async def dispatch(ws: WebSocket, msg: dict[str, Any], config: FsarConfig) -> bool:
    t = msg.get("type")
    if t == "reflection.set_intensity":
        intensity = msg.get("intensity", "")
        if intensity not in VALID_INTENSITY:
            await ws.send_json({"type": "error", "code": "bad_intensity", "message": intensity, "recoverable": True})
            return True
        config.patch("reflection.intensity", intensity)
        config.patch("memory.reflection_intensity", intensity)
        config.save()
        await ws.send_json({"type": "reflection.intensity_changed", "intensity": intensity})
        return True
    return False

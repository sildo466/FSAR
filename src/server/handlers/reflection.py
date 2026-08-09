# SPDX-License-Identifier: MIT
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
    if t == "reflection.list":
        from src.memory.reflection import ReflectionStore

        rows = ReflectionStore().list_recent(limit=int(msg.get("limit", 20)))
        events = [
            {
                "task_id": r.get("task_id", ""),
                "outcome": r.get("outcome", ""),
                "suggested_strategy": r.get("suggested_strategy") or "",
                "step_count": r.get("step_count", 0),
                "tools_used": r.get("tools_used") or [],
                "created_at": r.get("created_at", ""),
            }
            for r in rows
        ]
        await ws.send_json({"type": "reflection.list_result", "events": events})
        return True
    return False

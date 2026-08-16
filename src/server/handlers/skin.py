# SPDX-License-Identifier: MIT
"""WS dispatcher for skin list + activation (P1)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import WebSocket

from src.memory.skin_store import list_skins


def _skins_dir(config: Any | None) -> Path:
    if config is not None:
        return Path(config.get("data.skins_dir", "data/skins"))
    return Path("data/skins")


async def dispatch(ws: WebSocket, msg: dict[str, Any], config: Any | None = None) -> bool:
    t = msg.get("type")
    if not t or not t.startswith("skin."):
        return False
    if t == "skin.list":
        await ws.send_json({"type": "skin.list", "skins": list_skins(_skins_dir(config))})
        return True
    if t == "skin.set_active":
        skin_id = str(msg.get("skin_id") or "")
        if skin_id != "default" and not any(s["id"] == skin_id for s in list_skins(_skins_dir(config))):
            await ws.send_json({"type": "error", "code": "bad_skin", "message": skin_id, "recoverable": True})
            return True
        if config is not None:
            config.patch("style.skin_id", skin_id)
            try:
                config.save()
            except Exception:
                pass
        await ws.send_json({"type": "skin.changed", "skin_id": skin_id})
        return True
    return False

# SPDX-License-Identifier: MIT
"""WS dispatcher for the notification center."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import WebSocket

from src.notifications.store import KINDS, NotificationStore


def _store(config: Any) -> NotificationStore:
    path = config.get("memory.sqlite_path") if config is not None else None
    if not path:
        from src.utils.fsar_home import get_fsar_home

        path = get_fsar_home() / "data" / "memory.db"
    return NotificationStore(Path(path))


def _settings(config: Any) -> dict:
    get = (lambda key, default: config.get(key, default)) if config else (
        lambda key, default: default
    )
    return {
        "review": {"enabled": bool(get("notifications.review.enabled", True))},
        "release": {
            "enabled": bool(get("notifications.release.enabled", True)),
            "include_prerelease": bool(
                get("notifications.release.include_prerelease", False)
            ),
        },
        "announcement": {
            "enabled": bool(get("notifications.announcement.enabled", True))
        },
    }


async def _push_state(ws: WebSocket, store: NotificationStore, kind: str) -> None:
    await ws.send_json(
        {
            "type": kind,
            "unread": store.unread_count(),
        }
    )


async def dispatch(ws: WebSocket, msg: dict[str, Any], config: Any = None) -> bool:
    t = msg.get("type")
    if t == "notifications.list":
        store = _store(config)
        await ws.send_json(
            {
                "type": "notifications.list_result",
                "items": store.list(),
                "unread": store.unread_count(),
                "kinds": list(KINDS),
                "settings": _settings(config),
            }
        )
        return True
    if t == "notifications.mark_read":
        store = _store(config)
        raw = msg.get("ids")
        ids = [int(item) for item in raw] if isinstance(raw, list) else None
        store.mark_read(ids)
        await _push_state(ws, store, "notifications.read_result")
        return True
    if t == "notifications.clear":
        store = _store(config)
        store.clear()
        await _push_state(ws, store, "notifications.read_result")
        return True
    return False

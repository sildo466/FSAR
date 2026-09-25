# SPDX-License-Identifier: MIT
"""WS dispatcher for the content screening notification page."""

from __future__ import annotations

from typing import Any

from fastapi import WebSocket

from src.security.content_guard import SCAN_STORES


def _guard():
    from src.server import ws_server

    return ws_server._get_content_guard()


async def dispatch(ws: WebSocket, msg: dict[str, Any], ctx: dict[str, Any] | None = None) -> bool:
    t = msg.get("type")
    if t == "content_guard.list":
        guard = _guard()
        await ws.send_json(
            {
                "type": "content_guard.list_result",
                "items": guard.list_quarantine(),
                "whitelist": guard.list_whitelist(),
                "report": guard.get_report(),
                "stores": SCAN_STORES,
                "enabled": guard.enabled,
            }
        )
        return True
    if t in ("content_guard.restore", "content_guard.purge"):
        guard = _guard()
        qid = int(msg.get("id", 0))
        ok = guard.restore(qid) if t.endswith("restore") else guard.purge(qid)
        await ws.send_json(
            {
                "type": "content_guard.action_result",
                "action": t.split(".")[-1],
                "id": qid,
                "ok": ok,
            }
        )
        return True
    if t == "content_guard.unwhitelist":
        guard = _guard()
        sha = str(msg.get("sha256", ""))
        ok = guard.remove_hash_from_whitelist(sha)
        await ws.send_json(
            {
                "type": "content_guard.action_result",
                "action": "unwhitelist",
                "id": sha,
                "ok": ok,
            }
        )
        return True
    return False

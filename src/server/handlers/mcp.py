# SPDX-License-Identifier: MIT
"""WS dispatcher for MCP server control."""

from __future__ import annotations

from typing import Any

from fastapi import WebSocket


def _read_servers(config) -> list[dict[str, Any]]:
    servers = config.get("mcp.servers") or []
    if not isinstance(servers, list):
        return []
    return [s for s in servers if isinstance(s, dict)]


async def dispatch(ws: WebSocket, msg: dict[str, Any], ctx: dict[str, Any] | None = None) -> bool:
    t = msg.get("type")
    if t == "mcp.list":
        await _send_status(ws, ctx)
        return True
    if t == "mcp.reload":
        mgr = (ctx or {}).get("mcp_manager")
        if mgr is None:
            await ws.send_json({"type": "error", "code": "no_mcp_manager", "recoverable": False})
            return True
        try:
            await mgr.reload()
        except Exception as e:
            await ws.send_json({"type": "error", "code": "mcp_reload_failed", "message": str(e), "recoverable": True})
            return True
        await _send_status(ws, ctx)
        return True
    if t == "mcp.toggle":
        name = msg.get("server_name", "")
        enabled = bool(msg.get("enabled", True))
        if not name:
            await ws.send_json({"type": "error", "code": "no_server_name", "recoverable": True})
            return True
        config = (ctx or {}).get("config")
        if config is None:
            await ws.send_json({"type": "error", "code": "no_config", "recoverable": False})
            return True
        servers = _read_servers(config)
        found = False
        for s in servers:
            if s.get("name") == name:
                s["enabled"] = enabled
                found = True
                break
        if not found:
            await ws.send_json({"type": "error", "code": "server_not_found", "message": name, "recoverable": True})
            return True
        config.patch("mcp.servers", servers)
        try:
            config.save()
        except Exception:
            pass
        await _send_status(ws, ctx)
        return True
    return False


async def _send_status(ws: WebSocket, ctx: dict[str, Any] | None) -> None:
    config = (ctx or {}).get("config")
    servers = _read_servers(config) if config is not None else []
    live_names = set()
    mgr = (ctx or {}).get("mcp_manager")
    if mgr is not None:
        try:
            live_names = set(mgr.servers)
        except Exception:
            live_names = set()
    rows = []
    for s in servers:
        name = s.get("name", "")
        rows.append({
            "name": name,
            "command": s.get("command", ""),
            "args": s.get("args") or [],
            "enabled": bool(s.get("enabled", False)),
            "risk": s.get("risk_level", "HIGH"),
            "running": name in live_names,
        })
    await ws.send_json({"type": "mcp.status", "servers": rows})

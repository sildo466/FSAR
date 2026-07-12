# SPDX-License-Identifier: Apache-2.0
"""WS dispatcher for tool registry introspection.

The GUI's PermissionsTab asks for the live list of registered tools so it
can render per-tool permission overrides without hardcoding tool names.
"""

from __future__ import annotations

from typing import Any

from fastapi import WebSocket


def _resolve_engine(ctx: dict[str, Any] | None) -> Any | None:
    if not ctx:
        return None
    return ctx.get("engine")


async def dispatch(ws: WebSocket, msg: dict[str, Any], ctx: dict[str, Any] | None = None) -> bool:
    if msg.get("type") != "tools.list":
        return False
    engine = _resolve_engine(ctx)
    tools: list[dict[str, Any]] = []
    if engine is not None:
        try:
            for tool in sorted(engine.registry.list_tools(), key=lambda t: t.name):
                tools.append({
                    "name": tool.name,
                    "description": tool.description,
                    "risk_level": tool.risk_level,
                })
        except Exception:
            tools = []
    await ws.send_json({"type": "tools.list_result", "tools": tools})
    return True
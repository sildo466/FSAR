# SPDX-License-Identifier: Apache-2.0
"""WebSocket server — single endpoint /ws, JSON protocol."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from src.utils.fsar_config import FsarConfig
from src.utils.logger import logger
from src.server.handlers import chat as chat_handler
from src.server.handlers import insights as insights_handler
from src.server.handlers import library as library_handler
from src.server.handlers import memory as memory_handler
from src.server.handlers import mcp as mcp_handler
from src.server.handlers import reflection as reflection_handler
from src.server.handlers import risk as risk_handler
from src.server.handlers import settings as settings_handler
from src.server.handlers import usage as usage_handler
from src.server.risk_bridge import RiskBridge

app = FastAPI()
_config = FsarConfig()
_bridge = RiskBridge()
_ctx: dict[str, Any] = {"config": _config}
chat_handler.set_bridge(_bridge)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    await ws.send_json({"type": "snapshot", "config": _config._settings})
    try:
        while True:
            msg = await ws.receive_json()
            await _dispatch(msg, ws)
    except WebSocketDisconnect:
        logger.debug("ws client disconnected")


async def _dispatch(msg: dict[str, Any], ws: WebSocket) -> None:
    if await risk_handler.dispatch(_bridge, ws, msg):
        return
    if await reflection_handler.dispatch(ws, msg, _config):
        return
    if await settings_handler.dispatch(ws, msg, _config):
        return
    if await memory_handler.dispatch(ws, msg, _ctx):
        return
    if await library_handler.dispatch(ws, msg, _ctx):
        return
    if await mcp_handler.dispatch(ws, msg, _ctx):
        return
    if await insights_handler.dispatch(ws, msg, _ctx):
        return
    if await usage_handler.dispatch(ws, msg, _ctx):
        return
    if await chat_handler.dispatch(ws, msg):
        return
    if msg.get("type") == "heartbeat":
        await ws.send_json({"type": "heartbeat", "ts": 0})


def start(host: str = "127.0.0.1", port: int = 8765) -> None:
    """Run the server (blocking)."""
    import uvicorn

    uvicorn.run(app, host=host, port=port, log_level="info")
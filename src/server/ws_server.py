# SPDX-License-Identifier: Apache-2.0
"""WebSocket server — single endpoint /ws, JSON protocol."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from src.utils.fsar_config import FsarConfig
from src.utils.logger import logger

app = FastAPI()
_config = FsarConfig()


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
    """Placeholder dispatcher — replaced task by task in later phases."""
    if msg.get("type") == "heartbeat":
        await ws.send_json({"type": "heartbeat", "ts": 0})


def start(host: str = "127.0.0.1", port: int = 8765) -> None:
    """Run the server (blocking)."""
    import uvicorn

    uvicorn.run(app, host=host, port=port, log_level="info")

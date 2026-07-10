# SPDX-License-Identifier: Apache-2.0
"""WebSocket server — single endpoint /ws, JSON protocol."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.utils.fsar_config import FsarConfig
from src.utils.logger import logger
from src.server.handlers import chat as chat_handler
from src.server.handlers import card as card_handler
from src.server.handlers import conversation as conversation_handler
from src.server.handlers import insights as insights_handler
from src.server.handlers import library as library_handler
from src.server.handlers import memory as memory_handler
from src.server.handlers import mcp as mcp_handler
from src.server.handlers import onboarding as onboarding_handler
from src.server.handlers import provider as provider_handler
from src.server.handlers import reflection as reflection_handler
from src.server.handlers import risk as risk_handler
from src.server.handlers import settings as settings_handler
from src.server.handlers import tools as tools_handler
from src.server.handlers import usage as usage_handler
from src.server.risk_bridge import RiskBridge

from src.server.chat_engine import ChatEngine

def ensure_config(yaml_path: Path, template_path: Path) -> None:
    """First-run detection: copy template to yaml_path if yaml is missing.

    Raises FileNotFoundError if the template is also missing (cannot bootstrap).
    """
    if yaml_path.exists():
        return
    if not template_path.exists():
        raise FileNotFoundError(
            f"cannot bootstrap: template missing at {template_path}"
        )
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    yaml_path.write_text(template_path.read_text(encoding="utf-8"), encoding="utf-8")
    logger.info("First run: created %s from template", yaml_path)


app = FastAPI()
_config = FsarConfig()
_bridge = RiskBridge()
_engine = ChatEngine(_config, _bridge)
_ctx: dict[str, Any] = {
    "config": _config,
    "db_path": _config.get("memory.sqlite_path", "data/memory.db"),
    "cache_db_path": _config.llm_cache_db_path,
    "mcp_manager": _engine.mcp,
    "engine": _engine,
}
chat_handler.set_engine(_engine)
conversation_handler.set_engine(_engine)


@app.on_event("startup")
async def _startup() -> None:
    await _engine.start_mcp()
    from src.server.handlers.chat import _broadcast as _chat_broadcast
    def _listener(event_type, payload):
        # schedule broadcast; called from sync CardRepo methods
        import asyncio
        loop = asyncio.get_event_loop()
        loop.create_task(_chat_broadcast({"type": event_type, **payload}))
    _engine.card_repo.set_change_listener(_listener)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/card/{card_id}/avatar")
async def upload_avatar(card_id: int, request) -> dict[str, str]:
    """Persist avatar; body is raw bytes, X-FSAR-Avatar-Ext header has extension."""
    from fastapi import HTTPException
    from src.server.handlers.card import _get_card_repo
    ext = (request.headers.get("X-FSAR-Avatar-Ext") or "png").lower()
    if ext not in ("png", "jpg", "webp"):
        raise HTTPException(status_code=400, detail="bad_ext")
    body = await request.body()
    if len(body) > 2 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="too_large")
    repo = _get_card_repo(_ctx)
    avatar_path = repo.save_avatar(card_id, ext, body)
    return {"avatar_path": avatar_path}


@app.get("/api/fsar_yaml")
async def fsar_yaml() -> dict[str, str]:
    return {"yaml": yaml.safe_dump(_config._settings, allow_unicode=True, sort_keys=False)}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    chat_handler.register_socket(ws)
    await ws.send_json({"type": "snapshot", "config": _config._settings})
    sessions = _engine.session_store.list(limit=50)
    await ws.send_json({
        "type": "conversation.list",
        "sessions": [s.to_dict() for s in sessions],
    })
    try:
        while True:
            msg = await ws.receive_json()
            await _dispatch(msg, ws)
    except WebSocketDisconnect:
        logger.debug("ws client disconnected")
    finally:
        chat_handler.unregister_socket(ws)


async def _dispatch(msg: dict[str, Any], ws: WebSocket) -> None:
    if await risk_handler.dispatch(_bridge, ws, msg):
        return
    if await conversation_handler.dispatch(ws, msg):
        return
    if await card_handler.dispatch(ws, msg, _ctx):
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
    if await tools_handler.dispatch(ws, msg, _ctx):
        return
    if await usage_handler.dispatch(ws, msg, _ctx):
        return
    if await chat_handler.dispatch(ws, msg):
        return
    if await provider_handler.dispatch(ws, msg, _config):
        return
    if await onboarding_handler.dispatch(ws, msg, _config):
        return
    if msg.get("type") == "heartbeat":
        await ws.send_json({"type": "heartbeat", "ts": 0})


_FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def _mount_frontend(app: FastAPI) -> None:
    """Serve frontend/dist as the same-origin GUI.

    Layout (registered in order so specific routes win):
    1. /assets/* → StaticFiles (existing build artifacts)
    2. /         → index.html
    3. /<path>   → SPA fallback to index.html (so React Router can take over)
    """
    if not _FRONTEND_DIST.exists():
        @app.get("/", include_in_schema=False)
        async def _frontend_missing() -> dict[str, str]:
            return {
                "error": "frontend/dist not built",
                "hint": "cd frontend && npm install && npm run build",
            }
        return

    assets_dir = _FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    index_file = _FRONTEND_DIST / "index.html"

    @app.get("/", include_in_schema=False)
    async def _root() -> FileResponse:
        return FileResponse(str(index_file))

    @app.get("/{full_path:path}", include_in_schema=False)
    async def _spa(full_path: str) -> FileResponse:
        return FileResponse(str(index_file))


_mount_frontend(app)


def start(host: str = "127.0.0.1", port: int = 8765) -> None:
    """Run the server (blocking)."""
    import uvicorn

    config_path = Path("config/fsar.yaml")
    template_path = Path("config/fsar.yaml.template")
    ensure_config(config_path, template_path)
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    import sys

    # `python -m src.server.ws_server [host [port]]` for CLI convenience.
    start(*sys.argv[1:3])
# SPDX-License-Identifier: MIT
"""WebSocket server — single endpoint /ws, JSON protocol."""

from __future__ import annotations

import asyncio
import copy
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src.utils.fsar_config import get_default_config
from src.utils.logger import logger
from src.server.handlers import chat as chat_handler
from src.server.handlers import asr as asr_handler
from src.server.handlers import embedding as embedding_handler
from src.server.handlers import card as card_handler
from src.server.handlers import conversation as conversation_handler
from src.server.handlers import insights as insights_handler
from src.server.handlers import integration as integration_handler
from src.server.handlers import library as library_handler
from src.server.handlers import memory as memory_handler
from src.server.handlers import mcp as mcp_handler
from src.server.handlers import onboarding as onboarding_handler
from src.server.handlers import provider as provider_handler
from src.server.handlers import reflection as reflection_handler
from src.server.handlers import risk as risk_handler
from src.server.handlers import settings as settings_handler
from src.server.handlers import tts as tts_handler
from src.server.handlers import skill_install as skill_install_handler
from src.server.handlers import sandbox as sandbox_handler
from src.server.handlers import tools as tools_handler
from src.server.handlers import usage as usage_handler
from src.server import handlers as handlers_pkg
from src.server.risk_bridge import RiskBridge
from src.security.ws_auth import WSAuthenticator, bearer_token, websocket_token
from src.skills.keys import load_security_keys

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
    logger.info(f"First run: created {yaml_path} from template")


_CONFIG_TEMPLATE = Path(__file__).resolve().parents[2] / "config" / "fsar.yaml.template"
_config = get_default_config()
ensure_config(_config._path, _CONFIG_TEMPLATE)
_config.load()

app = FastAPI()
app.include_router(handlers_pkg.router)
_bridge = RiskBridge()
_engine = ChatEngine(_config, _bridge)
_ws_auth = WSAuthenticator()
_ctx: dict[str, Any] = {
    "config": _config,
    "db_path": _config.memory_sqlite_path,
    "mcp_manager": _engine.mcp,
    "engine": _engine,
    "workspace_repo": _engine.workspace_repo,
    "sandbox_bridge": _engine.sandbox_bridge,
}
chat_handler.set_engine(_engine)
conversation_handler.set_engine(_engine)

_feishu_adapter: Any = None
_wechat_adapter: Any = None
_social_router: Any = None
_social_adapters: list[Any] = []
_social_lock = asyncio.Lock()


def set_feishu_adapter(adapter: Any) -> None:
    global _feishu_adapter
    _feishu_adapter = adapter


def set_wechat_adapter(adapter: Any) -> None:
    global _wechat_adapter
    _wechat_adapter = adapter


async def _reload_social() -> None:
    global _social_router, _social_adapters
    from src.social.manager import (
        build_router_and_adapters,
        set_current_router,
        start_social,
        stop_social,
    )

    async with _social_lock:
        if _social_router is not None:
            await stop_social(_social_router, _social_adapters)
        set_feishu_adapter(None)
        set_wechat_adapter(None)
        _social_router, _social_adapters = build_router_and_adapters()
        set_current_router(_social_router)
        for adapter in _social_adapters:
            if adapter.name == "feishu":
                set_feishu_adapter(adapter)
            elif adapter.name == "wechat":
                set_wechat_adapter(adapter)
        await start_social(_social_router, _social_adapters)


@app.on_event("startup")
async def _startup() -> None:
    load_security_keys()
    _ws_auth.rotate()
    from src.server.chat_engine import set_default_chat_engine
    set_default_chat_engine(_engine)
    await _engine.start_mcp()
    from src.server.handlers.scheduler import set_engine as _set_sched_engine
    _set_sched_engine(_engine)
    from src.server.handlers.chat import _broadcast as _chat_broadcast
    def _listener(event_type, payload):
        # schedule broadcast; called from sync CardRepo methods
        import asyncio
        loop = asyncio.get_event_loop()
        loop.create_task(_chat_broadcast({"type": event_type, **payload}))
    _engine.card_repo.set_change_listener(_listener)
    seeded = _engine.card_repo.seed_builtins_if_empty()
    if seeded:
        logger.info(f"seeded {seeded} built-in card(s) from data/cards")
    renamed = _engine.card_repo.fix_builtin_display_names()
    if renamed:
        logger.info(f"renamed {renamed} built-in card(s) with language suffix")
    await _reload_social()


@app.on_event("shutdown")
async def _shutdown() -> None:
    global _social_router, _social_adapters
    from src.server.chat_engine import set_default_chat_engine
    set_default_chat_engine(None)
    if _social_router is not None:
        from src.social.manager import stop_social

        await stop_social(_social_router, _social_adapters)
    from src.social.manager import set_current_router
    set_current_router(None)
    set_feishu_adapter(None)
    set_wechat_adapter(None)
    _social_router = None
    _social_adapters = []
    await _engine.stop_mcp()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/social/feishu/webhook")
async def feishu_webhook(request: Request) -> Response:
    if _feishu_adapter is None:
        return Response(status_code=503)
    body = await request.body()
    if len(body) > 1024 * 1024:
        return Response(status_code=413)
    raw_response = _feishu_adapter.handle_webhook(
        body,
        dict(request.headers),
        request.url.path,
    )
    return Response(
        content=raw_response.content or b"",
        status_code=raw_response.status_code or 500,
        headers=raw_response.headers,
    )


@app.get("/api/social/status")
async def social_status(request: Request) -> dict[str, list[dict[str, Any]]]:
    if not _ws_auth.verify_token(bearer_token(request.headers.get("authorization"))):
        raise HTTPException(status_code=401, detail="unauthorized")
    statuses = {
        name: {"platform": name, "state": "paused", "configured": False}
        for name in ("telegram", "feishu", "wechat")
    }
    for adapter in _social_adapters:
        statuses[adapter.name] = {"configured": True, **adapter.status()}
    return {"statuses": list(statuses.values())}


@app.post("/api/social/wechat/qr")
async def wechat_qr(request: Request) -> dict[str, str]:
    if not _ws_auth.verify_token(bearer_token(request.headers.get("authorization"))):
        raise HTTPException(status_code=401, detail="unauthorized")
    if _wechat_adapter is None:
        raise HTTPException(status_code=503, detail="wechat_disabled")
    try:
        return await _wechat_adapter.begin_qr_login()
    except Exception as exc:
        logger.warning("wechat QR start failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/social/wechat/qr/reset")
async def wechat_qr_reset(request: Request) -> dict[str, str]:
    if not _ws_auth.verify_token(bearer_token(request.headers.get("authorization"))):
        raise HTTPException(status_code=401, detail="unauthorized")
    if _wechat_adapter is None:
        raise HTTPException(status_code=503, detail="wechat_disabled")
    try:
        return await _wechat_adapter.reset_qr_login()
    except Exception as exc:
        logger.warning("wechat QR reset failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/social/wechat/qr/status")
async def wechat_qr_status(request: Request) -> dict[str, str]:
    if not _ws_auth.verify_token(bearer_token(request.headers.get("authorization"))):
        raise HTTPException(status_code=401, detail="unauthorized")
    if _wechat_adapter is None:
        raise HTTPException(status_code=503, detail="wechat_disabled")
    try:
        return await _wechat_adapter.check_qr_login()
    except Exception as exc:
        logger.warning("wechat QR status failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/card/{card_id}/avatar")
async def upload_avatar(card_id: int, request: Request) -> dict[str, str]:
    """Persist avatar; body is raw bytes, X-FSAR-Avatar-Ext header has extension."""
    from fastapi import HTTPException
    from PIL import UnidentifiedImageError
    from src.server.handlers.card import _get_card_repo
    ext = (request.headers.get("X-FSAR-Avatar-Ext") or "png").lower()
    if ext not in ("png", "jpg", "webp"):
        raise HTTPException(status_code=400, detail="bad_ext")
    body = await request.body()
    if len(body) > 2 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="too_large")
    if len(body) == 0:
        logger.warning(f"avatar upload empty body for card {card_id}")
        raise HTTPException(status_code=400, detail="empty_body")
    repo = _get_card_repo(_ctx)
    try:
        avatar_path = repo.save_avatar(card_id, ext, body)
    except UnidentifiedImageError:
        raise HTTPException(status_code=400, detail="invalid_image")
    except Exception as e:
        logger.warning(f"avatar save_avatar failed for card {card_id} ext={ext} bytes={len(body)}: {e}")
        raise HTTPException(status_code=500, detail=f"save_failed: {type(e).__name__}: {e}")
    logger.info(f"avatar uploaded: card={card_id} ext={ext} bytes={len(body)} -> {avatar_path}")
    return {"avatar_path": avatar_path}


@app.get("/api/card/{card_id}/avatar")
async def get_avatar(card_id: int):
    from fastapi import HTTPException
    from fastapi.responses import FileResponse
    from src.server.handlers.card import _get_card_repo
    repo = _get_card_repo(_ctx)
    rel = repo.get_avatar_path(card_id)
    if not rel:
        raise HTTPException(status_code=404, detail="no_avatar")
    full = (Path(_ctx["db_path"]).parent / rel).resolve()
    if not full.exists():
        raise HTTPException(status_code=404, detail="missing_file")
    return FileResponse(
        str(full),
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store"},
    )


def _allowed_origins() -> list[str]:
    configured = _config.get("security.ws_auth.allowed_origins", []) or []
    return [item for item in configured if isinstance(item, str)]


def _request_metadata_allowed(request: Request) -> bool:
    return _ws_auth.request_allowed(
        host=request.headers.get("host", ""),
        origin=request.headers.get("origin"),
        allowed_origins=_allowed_origins(),
        fetch_site=request.headers.get("sec-fetch-site"),
        referer=request.headers.get("referer"),
    )


@app.get("/api/auth/ws-token")
async def ws_token(request: Request) -> JSONResponse:
    if not _request_metadata_allowed(request):
        raise HTTPException(status_code=403, detail="origin")
    return JSONResponse(
        {"token": _ws_auth.ensure_token()},
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


@app.get("/api/fsar_yaml")
async def fsar_yaml(request: Request) -> dict[str, str]:
    if not _request_metadata_allowed(request):
        raise HTTPException(status_code=403, detail="origin")
    if not _ws_auth.verify_token(bearer_token(request.headers.get("authorization"))):
        raise HTTPException(status_code=401, detail="auth")
    return {"yaml": yaml.safe_dump(_config._settings, allow_unicode=True, sort_keys=False)}


@app.post("/api/skill/install")
async def install_skill(request: Request) -> dict[str, object]:
    if not _request_metadata_allowed(request):
        raise HTTPException(status_code=403, detail="origin")
    if not _ws_auth.verify_token(bearer_token(request.headers.get("authorization"))):
        raise HTTPException(status_code=401, detail="auth")
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="bad_request")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="bad_request")
    folder_path = payload.get("folder_path")
    if not isinstance(folder_path, str) or not folder_path.strip():
        raise HTTPException(status_code=400, detail="bad_request")

    from src.tools.builtin.skill_folder import SkillFolderError

    try:
        result = skill_install_handler.install_skill_folder(folder_path, _ctx["db_path"])
    except SkillFolderError as exc:
        raise HTTPException(status_code=400, detail=exc.code)
    except Exception:
        logger.exception("skill folder persistence failed")
        raise HTTPException(status_code=500, detail="db_error")
    await chat_handler._broadcast({
        "type": "library.changed",
        "op": "install",
        "name": result["name"],
    })
    return result


@app.post("/api/chat/upload")
async def upload_chat_files(request: Request) -> dict[str, object]:
    """Store chat attachments under <FSAR_HOME>/uploads; returns saved paths."""
    if not _request_metadata_allowed(request):
        raise HTTPException(status_code=403, detail="origin")
    if not _ws_auth.verify_token(bearer_token(request.headers.get("authorization"))):
        raise HTTPException(status_code=401, detail="auth")
    try:
        form = await request.form()
    except Exception:
        raise HTTPException(status_code=400, detail="bad_request")
    files = form.getlist("files")
    if not files or len(files) > 8:
        raise HTTPException(status_code=400, detail="bad_request")

    import re
    import time

    from src.utils.fsar_home import get_fsar_home

    uploads_dir = get_fsar_home() / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    saved: list[dict[str, object]] = []
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for idx, item in enumerate(files):
        data = await item.read()
        if len(data) > 5 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="too_large")
        name = Path(item.filename or f"file{idx}").name
        safe = re.sub(r"[^\w.\-]+", "_", name)[:80] or f"file{idx}"
        dest = uploads_dir / f"{stamp}-{idx}-{safe}"
        dest.write_bytes(data)
        saved.append({"name": name, "path": str(dest), "size": len(data)})
    return {"files": saved}


@app.post("/api/skill/install/upload")
async def install_skill_upload(request: Request) -> dict[str, object]:
    """Browser fallback for skill install: multipart folder upload."""
    if not _request_metadata_allowed(request):
        raise HTTPException(status_code=403, detail="origin")
    if not _ws_auth.verify_token(bearer_token(request.headers.get("authorization"))):
        raise HTTPException(status_code=401, detail="auth")
    try:
        form = await request.form()
    except Exception:
        raise HTTPException(status_code=400, detail="bad_request")
    files = form.getlist("files")
    if not files or len(files) > 200:
        raise HTTPException(status_code=400, detail="bad_request")

    import shutil
    import tempfile

    from src.tools.builtin.skill_folder import SkillFolderError
    from src.utils.fsar_home import get_fsar_home

    staging = get_fsar_home() / "uploads" / "_skill_stage"
    staging.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(dir=staging))
    try:
        for item in files:
            rel = (item.filename or "").replace("\\", "/").strip()
            parts = Path(rel).parts
            if not rel or Path(rel).is_absolute() or ".." in parts:
                raise HTTPException(status_code=400, detail="bad_path")
            target = tmp / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(await item.read())
        result = skill_install_handler.install_skill_folder(tmp, _ctx["db_path"])
    except HTTPException:
        raise
    except SkillFolderError as exc:
        raise HTTPException(status_code=400, detail=exc.code)
    except Exception:
        logger.exception("skill folder upload persistence failed")
        raise HTTPException(status_code=500, detail="db_error")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    await chat_handler._broadcast({
        "type": "library.changed",
        "op": "install",
        "name": result["name"],
    })
    return result


@app.websocket("/ws/scheduler")
async def ws_scheduler(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        pass


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    client_id = ws.client.host if ws.client else "unknown"
    if _ws_auth.is_rate_limited(client_id):
        await ws.close(code=1008, reason="rate_limit")
        return
    allowed = _ws_auth.request_allowed(
        host=ws.headers.get("host", ""),
        origin=ws.headers.get("origin"),
        allowed_origins=_allowed_origins(),
        fetch_site=ws.headers.get("sec-fetch-site"),
        referer=ws.headers.get("referer"),
    )
    token = websocket_token(ws.headers.get("sec-websocket-protocol"))
    if not allowed or not _ws_auth.verify_token(token):
        _ws_auth.record_failure(client_id)
        await ws.close(code=1008, reason="auth")
        return
    await ws.accept(subprotocol="fsar-v1")
    chat_handler.register_socket(ws)
    onboarding_state = await onboarding_handler.onboarding_get_state(_config)
    from src.memory.integrations import list_integrations
    from src.providers.pricing import estimate_calls

    model_items = [
        {
            "kind": "model",
            "provider": provider.get("id", ""),
            "model": provider.get("model", ""),
            "label": provider.get("label") or provider.get("id", ""),
            "est_calls": 1,
        }
        for provider in _config.list_providers(enabled_only=True)
    ]
    integration_items = [
        {"kind": "integration", "id": item.id, "label": item.name,
         "est_calls": estimate_calls(item)}
        for item in list_integrations()
    ]
    await ws.send_json({
        "type": "snapshot",
        "config": _config._settings,
        "chat_models": model_items + integration_items,
        "selected_chat_model": _config.chat_default_model,
        "onboarding": {
            "required": onboarding_state["required"],
            "completed": onboarding_state["completed"],
            "completed_steps": onboarding_state["completed_steps"],
            "current_step": onboarding_state["current_step"],
        },
        **sandbox_handler.snapshot(_ctx, _engine.active_conversation_id()),
    })
    conversation_handler.prune_empty_sessions(
        _engine.session_store, _engine.active_conversation_id()
    )
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
    if await asr_handler.dispatch(ws, msg, _config):
        return
    if await sandbox_handler.dispatch(ws, msg, _ctx):
        return
    if await risk_handler.dispatch(_bridge, ws, msg):
        return
    if await conversation_handler.dispatch(ws, msg):
        return
    if await card_handler.dispatch(ws, msg, _ctx):
        return
    if await reflection_handler.dispatch(ws, msg, _config):
        return
    social_before = (
        copy.deepcopy(_config.get("social", {}))
        if msg.get("type") == "settings.patch"
        else None
    )
    if await settings_handler.dispatch(ws, msg, _config, _engine):
        if social_before is not None and social_before != _config.get("social", {}):
            await _reload_social()
        return
    if await tts_handler.dispatch(ws, msg, _config):
        return
    if await memory_handler.dispatch(ws, msg, _ctx):
        return
    if await library_handler.dispatch(ws, msg, _ctx):
        return
    if await mcp_handler.dispatch(ws, msg, _ctx):
        return
    if await insights_handler.dispatch(ws, msg, _ctx):
        return
    if await integration_handler.dispatch(ws, msg, _ctx):
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
    if await embedding_handler.dispatch(ws, msg, _config):
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

    config_path = _config._path
    ensure_config(config_path, _CONFIG_TEMPLATE)
    _config.load()
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    import sys

    # `python -m src.server.ws_server [host [port]]` for CLI convenience.
    start(*sys.argv[1:3])

"""WebSocket CRUD and test-panel handlers for integrations."""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

from fastapi import WebSocket

from src.memory.integrations import (
    CycleError,
    Integration,
    IntegrationSub,
    ModelSpec,
    NotFoundError,
    delete_integration,
    finish_run,
    get_integration,
    get_model,
    list_integrations,
    list_models,
    upsert_integration,
    upsert_model,
)
from src.providers.pricing import estimate_calls
from src.server.integration_engine import execute_detailed

_replay_runs: dict[str, dict[str, Any]] = {}


def _payload(msg: dict[str, Any]) -> dict[str, Any]:
    payload = msg.get("payload")
    return payload if isinstance(payload, dict) else msg


def _snapshot(intg: Integration) -> dict[str, Any]:
    result = intg.to_dict()
    result["main_model"] = get_model(intg.main_model_id).to_dict()
    result["subs"] = [
        {
            **sub.to_dict(),
            "model": get_model(sub.model_id).to_dict() if sub.kind == "model" and sub.model_id else None,
            "child": get_integration(sub.child_integration_id).to_dict()
            if sub.kind == "integration" and sub.child_integration_id else None,
        }
        for sub in intg.subs
    ]
    result["est_calls"] = estimate_calls(intg)
    return result


def _model_from_payload(raw: dict[str, Any], existing_id: int | None = None) -> ModelSpec:
    return ModelSpec(
        id=existing_id or raw.get("id"),
        provider=str(raw.get("provider", "openai")),
        base_url=str(raw.get("base_url", "")),
        api_key=str(raw.get("api_key", "")),
        protocol=str(raw.get("protocol", "")),
        model=str(raw.get("model", "gpt-4o-mini")),
        persona_prompt=str(raw.get("persona_prompt", raw.get("persona", "You are a specialist."))),
        specialty=str(raw.get("specialty", "")),
        temperature=float(raw.get("temperature", 0.7)),
        max_tokens=raw.get("max_tokens"),
    )


def _integration_from_payload(raw: dict[str, Any]) -> Integration:
    main_id = raw.get("main_model_id")
    main = raw.get("main_model")
    if isinstance(main, dict):
        main_id = upsert_model(_model_from_payload(main, existing_id=int(main_id) if int(main_id or 0) > 0 else None))
    if main_id is None:
        models = list_models()
        main_id = models[0].id if models else upsert_model(_model_from_payload({}))
    subs: list[IntegrationSub] = []
    for position, value in enumerate(raw.get("subs") or []):
        if not isinstance(value, dict):
            continue
        kind = str(value.get("kind", "model"))
        model_id = value.get("model_id")
        child_id = value.get("child_integration_id")
        if kind == "model" and isinstance(value.get("model"), dict):
            model_id = upsert_model(_model_from_payload(
                value["model"], existing_id=int(model_id) if int(model_id or 0) > 0 else None,
            ))
        subs.append(IntegrationSub(
            id=value.get("id"), position=position,
            display_name=str(value.get("display_name", value.get("name", f"Sub {position + 1}"))),
            kind=kind, model_id=model_id, child_integration_id=child_id,
        ))
    return Integration(
        id=raw.get("id"), name=str(raw.get("name", "New Intergration")),
        description=str(raw.get("description", "")), main_model_id=int(main_id),
        rounds=int(raw.get("rounds", 2)), max_depth=int(raw.get("max_depth", 2)),
        max_subs_picked=raw.get("max_subs_picked", 2), is_default=int(raw.get("is_default", 0)),
        subs=subs,
    )


def _emit(ws: Any, message: dict[str, Any]) -> None:
    if ws is None:
        return
    emit = getattr(ws, "emit", None)
    if callable(emit):
        emit(message)
        return
    send = getattr(ws, "send_json", None)
    if callable(send):
        result = send(message)
        if asyncio.iscoroutine(result):
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                asyncio.run(result)
            else:
                loop.create_task(result)


def handle_run(msg: dict[str, Any], ws: Any = None) -> dict[str, Any]:
    payload = _payload(msg)
    integration_id = int(payload.get("id", payload.get("integration_id")))
    message = str(payload.get("message", ""))
    mode = str(payload.get("mode", "replay"))
    run_id = str(uuid.uuid4())
    intg = get_integration(integration_id)
    _emit(ws, {"type": "integration.run_started", "run_id": run_id,
               "integration_id": integration_id, "sub_count": len(intg.subs)})
    if mode == "estimate":
        total = estimate_calls(intg)
        final = {"type": "integration.run_done", "run_id": run_id, "status": "ok",
                 "total_calls": total, "total_calls_only": total,
                 "total_cost_usd": None, "total_ms": 0, "mode": "estimate"}
        _emit(ws, final)
        return final
    started = time.monotonic()
    text, trace = execute_detailed({"kind": "integration", "id": integration_id}, message)
    route = trace.route or {"selected": [], "reasoning": ""}
    _emit(ws, {"type": "integration.routing_done", "run_id": run_id,
               "selected": route.get("selected", []), "reasoning": route.get("reasoning", "")})
    selected = set(route.get("selected", []))
    chosen = [s for s in intg.subs if s.display_name in selected]
    for sub in chosen:
        _emit(ws, {"type": "integration.sub_started", "run_id": run_id, "sub_id": sub.display_name})
        _emit(ws, {"type": "integration.sub_done", "run_id": run_id, "sub_id": sub.display_name,
                   "ms": 0, "ok": True})
    for entry in trace.debate:
        replies = entry.get("replies", {})
        _emit(ws, {"type": "integration.debate_round_done", "run_id": run_id,
                   "round": entry.get("round", 0),
                   "all_consensus": bool(replies) and all("[consensus]" in str(v).lower() for v in replies.values())})
    _replay_runs[run_id] = {"rounds": trace.debate, "route": route, "final_reply": text}
    final = {"type": "integration.run_done", "run_id": run_id, "status": "ok",
             "total_calls": trace.calls, "total_cost_usd": trace.total_cost_usd,
             "total_ms": int((time.monotonic() - started) * 1000),
             "mode": "replay", "final_reply": text, "errors": trace.errors}
    _emit(ws, final)
    return final


async def dispatch(ws: WebSocket, msg: dict[str, Any], ctx: dict[str, Any] | None = None) -> bool:
    kind = msg.get("type")
    if kind == "integration.list":
        await ws.send_json({"type": "integration.list_result", "items": [_snapshot(i) for i in list_integrations()],
                            "models": [m.to_dict() for m in list_models()]})
        return True
    if kind == "integration.save":
        try:
            intg = _integration_from_payload(_payload(msg))
            integration_id = upsert_integration(intg)
            await ws.send_json({"type": "integration.saved", "id": integration_id,
                                "integration": _snapshot(get_integration(integration_id))})
        except CycleError as exc:
            await ws.send_json({"type": "integration.error", "code": "cycle", "path": exc.path,
                                "message": str(exc)})
        except Exception as exc:
            await ws.send_json({"type": "integration.error", "code": "save_failed", "message": str(exc)})
        return True
    if kind == "integration.delete":
        try:
            deleted_id = int(_payload(msg).get("id"))
            delete_integration(deleted_id)
            if ctx and ctx.get("config"):
                config = ctx["config"]
                selected = config.chat_default_model
                if selected.get("kind") == "integration" and int(selected.get("id", -1)) == deleted_id:
                    fallback = {"kind": "model", "provider": config.get("llm.active", ""),
                                "model": config.get_active_provider().get("model", "")}
                    config.patch("chat.default_model", fallback)
                    try:
                        config.save()
                    except Exception:
                        pass
                    await ws.send_json({"type": "chat.default_model_fallback", "selected_chat_model": fallback})
            await ws.send_json({"type": "integration.deleted", "id": deleted_id})
        except Exception as exc:
            await ws.send_json({"type": "integration.error", "code": "delete_failed", "message": str(exc)})
        return True
    if kind == "integration.run":
        events: list[dict[str, Any]] = []

        class _Sink:
            def emit(self, event: dict[str, Any]) -> None:
                events.append(event)

        result = await asyncio.to_thread(handle_run, msg, _Sink())
        for event in events:
            await ws.send_json(event)
        return result is not None
    if kind == "integration.run_sub_replies":
        run_id = str(_payload(msg).get("run_id", ""))
        await ws.send_json({"type": "integration.run_sub_replies_result", "run_id": run_id,
                            **(_replay_runs.get(run_id) or {"rounds": []})})
        return True
    return False


__all__ = ["dispatch", "handle_run"]

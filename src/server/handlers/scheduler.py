"""Scheduler REST endpoints — CRUD on user jobs + run-now + run history.

Endpoint surface per spec §8.1:
  GET    /jobs                  list (optional ?enabled=)
  GET    /jobs/{id}             detail
  POST   /jobs                  create
  PATCH  /jobs/{id}            update (incl enable/disable)
  DELETE /jobs/{id}             delete (cascades runs)
  POST   /jobs/{id}/run         force run-now
  GET    /runs?job_id=&status=  list runs
  GET    /system-jobs           B-layer seeds (read-only)
  PATCH  /system-jobs/{id}      toggle enabled
  GET    /handlers              SYSTEM_HANDLERS keys (for UI display)

Engine reference is set via set_engine() in ws_server startup.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

from src.scheduler.types import (
    DeliveryMode, JobKind, ScheduleKind, ScheduledJob,
)
from src.scheduler.seed import SYSTEM_HANDLERS
from src.scheduler.executor import BLOCKED_TOOLS
from src.scheduler.triggers import build_trigger, parse_at, parse_interval

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])

_engine_ref: dict[str, Any] = {}


def set_engine(engine) -> None:
    _engine_ref["engine"] = engine


def _svc():
    engine = _engine_ref.get("engine")
    svc = getattr(engine, "scheduler", None) if engine is not None else None
    if svc is None:
        raise HTTPException(status_code=503, detail="scheduler not initialized")
    return svc


def _store():
    return _svc()._store


def _job_to_dict(j: ScheduledJob) -> dict:
    return {
        "id": j.id,
        "name": j.name,
        "description": j.description,
        "enabled": j.enabled,
        "schedule_kind": j.schedule_kind.value,
        "schedule_expr": j.schedule_expr,
        "timezone": j.timezone,
        "job_kind": j.job_kind.value,
        "prompt": j.prompt,
        "tools_allow": json.loads(j.tools_allow) if j.tools_allow else [],
        "model_override": j.model_override,
        "timeout_seconds": j.timeout_seconds,
        "delivery_mode": j.delivery_mode.value,
        "delivery_target": j.delivery_target,
        "running_at": j.running_at.isoformat() if j.running_at else None,
        "last_run_at": j.last_run_at.isoformat() if j.last_run_at else None,
        "last_status": j.last_status.value if j.last_status else None,
        "last_error": j.last_error,
        "consecutive_errors": j.consecutive_errors,
        "created_at": j.created_at.isoformat(),
        "updated_at": j.updated_at.isoformat(),
    }


def _parse_schedule(kind: str, expr: str, tz: str = "") -> tuple[ScheduleKind, str]:
    try:
        sk = ScheduleKind(kind)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"invalid schedule_kind: {kind}")
    if sk == ScheduleKind.CRON:
        try:
            from apscheduler.triggers.cron import CronTrigger
            CronTrigger.from_crontab(expr)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"invalid cron expr: {e}")
    elif sk == ScheduleKind.INTERVAL:
        try:
            parse_interval(expr)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
    elif sk == ScheduleKind.AT:
        try:
            target = parse_at(expr, tz)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=f"invalid at timestamp: {e}")
        if target <= datetime.now(timezone.utc):
            raise HTTPException(status_code=422, detail="at timestamp must be in the future")
    elif sk == ScheduleKind.STARTUP:
        pass
    return sk, expr


def _validate_tools_allow(raw) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raise HTTPException(status_code=422, detail="tools_allow must be a JSON array")
    if not isinstance(raw, list):
        raise HTTPException(status_code=422, detail="tools_allow must be a list")
    blocked = [n for n in raw if isinstance(n, str) and n in BLOCKED_TOOLS]
    if blocked:
        raise HTTPException(
            status_code=422,
            detail=f"these tools are not allowed for scheduled jobs: {blocked}",
        )
    return [n for n in raw if isinstance(n, str)]


def _validate_delivery(mode: str, target: str) -> tuple[DeliveryMode, str]:
    try:
        dm = DeliveryMode(mode)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"invalid delivery_mode: {mode}")
    if dm == DeliveryMode.SOCIAL:
        if not target:
            raise HTTPException(status_code=422, detail="delivery_target required for social delivery")
        if target == "wechat":
            # Bare 'wechat' resolves to the bot owner's default DM.
            return dm, target
        parts = target.split(":", 2)
        if len(parts) != 3 or parts[0] not in ("feishu", "telegram", "wechat") \
           or parts[1] not in ("user", "chat", "group") or not parts[2]:
            raise HTTPException(
                status_code=422,
                detail="delivery_target must be '<platform>:<kind>:<id>' "
                       "(platforms: feishu|telegram|wechat; kinds: user|chat|group) "
                       "or 'wechat' for the default DM",
            )
    return dm, target


@router.get("/health")
async def scheduler_health() -> dict:
    try:
        svc = _svc()
        return {
            "status": "ok",
            "registered_jobs": len(svc._registered),
            "in_flight": len([t for t in svc._in_flight if not t.done()]),
        }
    except HTTPException:
        return {"status": "starting"}


@router.get("/handlers")
async def list_handlers() -> dict:
    return {"handlers": sorted(SYSTEM_HANDLERS.keys())}


@router.get("/jobs")
async def list_jobs(enabled: Optional[bool] = None) -> dict:
    jobs = _store().list_jobs(enabled_only=enabled)
    return {"jobs": [_job_to_dict(j) for j in jobs]}


@router.get("/jobs/{job_id}")
async def get_job(job_id: int) -> dict:
    j = _store().get_job(job_id)
    if j is None:
        raise HTTPException(status_code=404, detail="job not found")
    return _job_to_dict(j)


@router.post("/jobs")
async def create_job(payload: dict) -> dict:
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="name required")
    if _store().get_job_by_name(name):
        raise HTTPException(status_code=422, detail=f"job name already exists: {name}")

    sk, expr = _parse_schedule(
        payload.get("schedule_kind", "cron"),
        payload.get("schedule_expr", ""),
        payload.get("timezone", ""),
    )
    tools_allow = _validate_tools_allow(payload.get("tools_allow", []))
    dm, target = _validate_delivery(
        payload.get("delivery_mode", "db_only"),
        payload.get("delivery_target", ""),
    )

    now = datetime.now(timezone.utc)
    j = ScheduledJob(
        id=0,
        name=name,
        description=payload.get("description", ""),
        enabled=bool(payload.get("enabled", True)),
        schedule_kind=sk,
        schedule_expr=expr,
        timezone=payload.get("timezone", ""),
        job_kind=JobKind.AGENT,
        prompt=payload.get("prompt", ""),
        tools_allow=json.dumps(tools_allow),
        model_override=payload.get("model_override", ""),
        timeout_seconds=int(payload.get("timeout_seconds", 60)),
        delivery_mode=dm,
        delivery_target=target,
        running_at=None,
        last_run_at=None,
        last_status=None,
        last_error="",
        consecutive_errors=0,
        created_at=now,
        updated_at=now,
    )
    jid = _store().create_job(j)
    _svc().reload_job(jid)
    created = _store().get_job(jid)
    return _job_to_dict(created)


@router.patch("/jobs/{job_id}")
async def update_job(job_id: int, payload: dict) -> dict:
    existing = _store().get_job(job_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="job not found")

    patch: dict = {}
    if "name" in payload:
        name = (payload["name"] or "").strip()
        if not name:
            raise HTTPException(status_code=422, detail="name required")
        if name != existing.name and _store().get_job_by_name(name):
            raise HTTPException(status_code=422, detail=f"job name already exists: {name}")
        patch["name"] = name
    if "description" in payload:
        patch["description"] = payload["description"]
    if "enabled" in payload:
        patch["enabled"] = bool(payload["enabled"])
    if "prompt" in payload:
        patch["prompt"] = payload["prompt"]
    if "timeout_seconds" in payload:
        patch["timeout_seconds"] = int(payload["timeout_seconds"])
    if "model_override" in payload:
        patch["model_override"] = payload["model_override"]
    if "delivery_target" in payload:
        patch["delivery_target"] = payload["delivery_target"]
    if "tools_allow" in payload:
        tools_allow = _validate_tools_allow(payload["tools_allow"])
        patch["tools_allow"] = json.dumps(tools_allow)
    if "schedule_kind" in payload or "schedule_expr" in payload or "timezone" in payload:
        sk, expr = _parse_schedule(
            payload.get("schedule_kind", existing.schedule_kind.value),
            payload.get("schedule_expr", existing.schedule_expr),
            payload.get("timezone", existing.timezone),
        )
        patch["schedule_kind"] = sk
        patch["schedule_expr"] = expr
        patch["timezone"] = payload.get("timezone", existing.timezone)
    if "delivery_mode" in payload:
        dm, target = _validate_delivery(
            payload["delivery_mode"],
            payload.get("delivery_target", existing.delivery_target),
        )
        patch["delivery_mode"] = dm
        patch["delivery_target"] = target

    _store().update_job(job_id, patch)
    _svc().reload_job(job_id)
    return _job_to_dict(_store().get_job(job_id))


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: int) -> dict:
    if _store().delete_job(job_id):
        _svc().reload_job(job_id)
        return {"deleted": job_id}
    raise HTTPException(status_code=404, detail="job not found")


@router.post("/jobs/{job_id}/run")
async def run_now(job_id: int) -> dict:
    import asyncio
    if _store().get_job(job_id) is None:
        raise HTTPException(status_code=404, detail="job not found")
    asyncio.create_task(_svc()._on_trigger(job_id))
    return {"queued": job_id}


@router.get("/runs")
async def list_runs(
    job_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
) -> dict:
    from src.scheduler.types import RunStatus
    rs = RunStatus(status) if status else None
    runs = _store().list_runs(job_id=job_id, status=rs, limit=limit)
    return {
        "runs": [
            {
                "id": r.id,
                "job_id": r.job_id,
                "expected_at": r.expected_at.isoformat() if r.expected_at else None,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "duration_ms": r.duration_ms,
                "status": r.status.value,
                "error": r.error,
                "error_class": r.error_class,
                "result_text": r.result_text,
                "delivery_status": r.delivery_status,
                "delivery_error": r.delivery_error,
                "created_at": r.created_at.isoformat(),
            }
            for r in runs
        ],
    }


@router.get("/system-jobs")
async def list_system_jobs() -> dict:
    jobs = _store().list_jobs()
    return {
        "jobs": [
            _job_to_dict(j) for j in jobs
            if j.name in SYSTEM_HANDLERS
        ],
    }


@router.patch("/system-jobs/{job_id}")
async def toggle_system_job(job_id: int, payload: dict) -> dict:
    j = _store().get_job(job_id)
    if j is None or j.name not in SYSTEM_HANDLERS:
        raise HTTPException(status_code=404, detail="system job not found")
    if "enabled" not in payload:
        raise HTTPException(status_code=422, detail="only 'enabled' field is mutable")
    _store().update_job(job_id, {"enabled": bool(payload["enabled"])})
    _svc().reload_job(job_id)
    return _job_to_dict(_store().get_job(job_id))
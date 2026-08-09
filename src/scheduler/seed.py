"""B-layer system job seed + real handlers.

Six handlers wired to actual FSAR subsystems:
- idle_reflect: IdleReflector.reflect(force=True)
- exp_mark_stale / exp_mark_archived: ExperienceStore lifecycle
- llm_l2_sweep: expired-entry cleanup from LLM L2 SQLite cache
- tts_cache_sweep: TTS L2 size-based eviction
- audit_rotate: monthly rotation of data/logs/audit.log

seed_defaults(store) is idempotent.
"""
from __future__ import annotations

import gzip
import json
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from src.scheduler.types import (
    DeliveryMode, JobKind, ScheduleKind, ScheduledJob,
)

if TYPE_CHECKING:
    from src.scheduler.store import JobStore


# ---------- Handlers ----------

async def _idle_reflect_handler(ctx) -> dict:
    from src.memory.reflection import IdleReflector
    reflector = IdleReflector()
    report = reflector.reflect(force=True)
    if report is None:
        return {"ok": True, "summary": "no report (no LLM or insufficient data)"}
    return {
        "ok": True,
        "summary": f"profile={len(report.profile)} prefs={len(report.preferences)} patterns={len(report.patterns)}",
    }


async def _exp_mark_stale_handler(ctx) -> dict:
    from src.memory.experience_store import ExperienceStore
    n = ExperienceStore().mark_stale(days=30)
    return {"ok": True, "summary": f"marked {n} experiences stale"}


async def _exp_mark_archived_handler(ctx) -> dict:
    from src.memory.experience_store import ExperienceStore
    n = ExperienceStore().mark_archived(days=90)
    return {"ok": True, "summary": f"archived {n} experiences"}


async def _llm_l2_sweep_handler(ctx) -> dict:
    from src.utils.fsar_config import get_config
    cfg = get_config()
    db_path = Path(cfg.llm_cache_db_path)
    if not db_path.exists():
        return {"ok": True, "summary": "no L2 cache file"}
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(db_path, timeout=10) as conn:
        cur = conn.execute("DELETE FROM llm_cache WHERE expires_at < ?", (now,))
        conn.commit()
    return {"ok": True, "summary": f"deleted {cur.rowcount} expired entries"}


async def _tts_cache_sweep_handler(ctx) -> dict:
    from src.providers.tts.cache import l2_compact
    before_size = 0
    try:
        from src.providers.tts.cache import l2_total_bytes
        before_size = l2_total_bytes()
    except Exception:
        pass
    l2_compact()
    return {"ok": True, "summary": f"compacted (was {before_size} bytes)"}


async def _audit_rotate_handler(ctx) -> dict:
    from src.utils.fsar_home import get_fsar_home
    log_path = get_fsar_home() / "data" / "logs" / "audit.log"
    if not log_path.exists():
        return {"ok": True, "summary": "no audit log"}
    archive_name = f"fsar_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.log"
    archive_path = log_path.parent / archive_name
    if archive_path.exists():
        suffix = datetime.now(timezone.utc).strftime('%H%M%S')
        archive_path = log_path.parent / f"fsar_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M%S')}.log"
    shutil.move(str(log_path), str(archive_path))
    return {"ok": True, "summary": f"archived to {archive_path.name}"}


SYSTEM_HANDLERS = {
    "idle_reflect":      _idle_reflect_handler,
    "exp_mark_stale":    _exp_mark_stale_handler,
    "exp_mark_archived": _exp_mark_archived_handler,
    "llm_l2_sweep":      _llm_l2_sweep_handler,
    "tts_cache_sweep":   _tts_cache_sweep_handler,
    "audit_rotate":      _audit_rotate_handler,
}


def _job(
    name: str, schedule_kind: ScheduleKind, schedule_expr: str,
    description: str = "",
) -> ScheduledJob:
    now = datetime.now(timezone.utc)
    return ScheduledJob(
        id=0,
        name=name,
        description=description,
        enabled=True,
        schedule_kind=schedule_kind,
        schedule_expr=schedule_expr,
        timezone="",
        job_kind=JobKind.SYSTEM,
        prompt="",
        tools_allow="",
        model_override="",
        timeout_seconds=300,
        delivery_mode=DeliveryMode.DB_ONLY,
        delivery_target="",
        running_at=None,
        last_run_at=None,
        last_status=None,
        last_error="",
        consecutive_errors=0,
        created_at=now,
        updated_at=now,
    )


DEFAULT_SEED_JOBS: list[ScheduledJob] = [
    _job("idle_reflect",      ScheduleKind.INTERVAL, "12h",
         "Run IdleReflector to update profile/preferences/patterns."),
    _job("exp_mark_stale",    ScheduleKind.CRON,     "0 3 * * *",
         "Mark experiences stale if not used in 30 days."),
    _job("exp_mark_archived", ScheduleKind.CRON,     "0 4 * * 0",
         "Archive experiences stale for 90 days."),
    _job("llm_l2_sweep",      ScheduleKind.INTERVAL, "1h",
         "Sweep expired entries from LLM L2 SQLite cache."),
    _job("tts_cache_sweep",   ScheduleKind.INTERVAL, "6h",
         "Compact TTS L2 cache to L2_MAX_BYTES."),
    _job("audit_rotate",      ScheduleKind.CRON,     "0 5 1 * *",
         "Rotate data/logs/audit.log monthly."),
]


def seed_defaults(store: "JobStore") -> int:
    """Insert DEFAULT_SEED_JOBS rows if table is empty."""
    existing = store.list_jobs()
    if existing:
        return 0
    inserted = 0
    for job in DEFAULT_SEED_JOBS:
        store.create_job(job)
        inserted += 1
    return inserted
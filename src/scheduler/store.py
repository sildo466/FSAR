"""JobStore — SQLite persistence for scheduled_jobs + job_runs.

Atomic claim lock semantics:
  UPDATE scheduled_jobs SET running_at=? WHERE id=? AND enabled=1
    AND (running_at IS NULL OR running_at < ? - INTERVAL '1 hour')
The 1-hour grace prevents zombie locks from permanently blocking a job after
a process crash. The health tick in service.py also force-releases stale locks.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

from src.scheduler.types import (
    DeliveryMode, JobKind, JobRun, RunStatus, ScheduleKind, ScheduledJob,
)


_ROW_TO_JOB = """
INSERT INTO scheduled_jobs
  (name, description, enabled,
   schedule_kind, schedule_expr, timezone,
   job_kind, prompt, tools_allow, model_override, timeout_seconds,
   delivery_mode, delivery_target,
   running_at, last_run_at, last_status, last_error, consecutive_errors,
   created_at, updated_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_JOB_COLS = (
    "id", "name", "description", "enabled",
    "schedule_kind", "schedule_expr", "timezone",
    "job_kind", "prompt", "tools_allow", "model_override", "timeout_seconds",
    "delivery_mode", "delivery_target",
    "running_at", "last_run_at", "last_status", "last_error", "consecutive_errors",
    "created_at", "updated_at",
)


def _row_to_job(row: sqlite3.Row) -> ScheduledJob:
    def _dt(v: str | None) -> datetime | None:
        if v is None:
            return None
        return datetime.fromisoformat(v)

    return ScheduledJob(
        id=row["id"],
        name=row["name"],
        description=row["description"] or "",
        enabled=bool(row["enabled"]),
        schedule_kind=ScheduleKind(row["schedule_kind"]),
        schedule_expr=row["schedule_expr"],
        timezone=row["timezone"] or "",
        job_kind=JobKind(row["job_kind"]),
        prompt=row["prompt"] or "",
        tools_allow=row["tools_allow"] or "",
        model_override=row["model_override"] or "",
        timeout_seconds=row["timeout_seconds"],
        delivery_mode=DeliveryMode(row["delivery_mode"]),
        delivery_target=row["delivery_target"] or "",
        running_at=_dt(row["running_at"]),
        last_run_at=_dt(row["last_run_at"]),
        last_status=RunStatus(row["last_status"]) if row["last_status"] else None,
        last_error=row["last_error"] or "",
        consecutive_errors=row["consecutive_errors"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _row_to_run(row: sqlite3.Row) -> JobRun:
    def _dt(v: str | None) -> datetime | None:
        return datetime.fromisoformat(v) if v else None

    return JobRun(
        id=row["id"],
        job_id=row["job_id"],
        expected_at=_dt(row["expected_at"]),
        started_at=_dt(row["started_at"]),
        finished_at=_dt(row["finished_at"]),
        duration_ms=row["duration_ms"],
        status=RunStatus(row["status"]),
        error=row["error"] or "",
        error_class=row["error_class"] or "",
        result_text=row["result_text"] or "",
        delivery_status=row["delivery_status"] or "",
        delivery_error=row["delivery_error"] or "",
        created_at=datetime.fromisoformat(row["created_at"]),
    )


class JobStore:
    def __init__(self, db_path: str | Path = "data/scheduler.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
        finally:
            conn.close()

    def ensure_tables(self) -> None:
        from src.scheduler.migrations._runner import apply_sql
        apply_sql(self.db_path, "0001_init.sql")

    # ---------- CRUD ----------

    def create_job(self, job: ScheduledJob) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                _ROW_TO_JOB,
                (
                    job.name, job.description, int(job.enabled),
                    job.schedule_kind.value, job.schedule_expr, job.timezone,
                    job.job_kind.value, job.prompt, job.tools_allow,
                    job.model_override, job.timeout_seconds,
                    job.delivery_mode.value, job.delivery_target,
                    job.running_at.isoformat() if job.running_at else None,
                    job.last_run_at.isoformat() if job.last_run_at else None,
                    job.last_status.value if job.last_status else None,
                    job.last_error, job.consecutive_errors,
                    job.created_at.isoformat(), job.updated_at.isoformat(),
                ),
            )
            return cur.lastrowid or 0

    def get_job(self, job_id: int) -> ScheduledJob | None:
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT {_JOB_COLS_STR} FROM scheduled_jobs WHERE id=?",
                (job_id,),
            ).fetchone()
            return _row_to_job(row) if row else None

    def get_job_by_name(self, name: str) -> ScheduledJob | None:
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT {_JOB_COLS_STR} FROM scheduled_jobs WHERE name=?",
                (name,),
            ).fetchone()
            return _row_to_job(row) if row else None

    def list_jobs(self, *, enabled_only: bool = False) -> list[ScheduledJob]:
        cols = ", ".join(_JOB_COLS)
        sql = f"SELECT {cols} FROM scheduled_jobs"
        if enabled_only:
            sql += " WHERE enabled=1"
        sql += " ORDER BY id"
        with self._connect() as conn:
            return [_row_to_job(r) for r in conn.execute(sql).fetchall()]

    def update_job(self, job_id: int, patch: dict) -> bool:
        if not patch:
            return False
        cols = []
        vals = []
        for k, v in patch.items():
            if k not in _JOB_COLS or k == "id":
                continue
            if isinstance(v, bool):
                vals.append(int(v)); cols.append(f"{k}=?")
            elif isinstance(v, ScheduleKind):
                vals.append(v.value); cols.append(f"{k}=?")
            elif isinstance(v, JobKind):
                vals.append(v.value); cols.append(f"{k}=?")
            elif isinstance(v, DeliveryMode):
                vals.append(v.value); cols.append(f"{k}=?")
            elif isinstance(v, RunStatus):
                vals.append(v.value); cols.append(f"{k}=?")
            elif isinstance(v, datetime):
                vals.append(v.isoformat()); cols.append(f"{k}=?")
            else:
                vals.append(v); cols.append(f"{k}=?")
        vals.append(datetime.now(timezone.utc).isoformat())
        cols.append("updated_at=?")
        sql = f"UPDATE scheduled_jobs SET {', '.join(cols)} WHERE id=?"
        vals.append(job_id)
        with self._connect() as conn:
            cur = conn.execute(sql, vals)
            return cur.rowcount > 0

    def delete_job(self, job_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM scheduled_jobs WHERE id=?", (job_id,))
            return cur.rowcount > 0

    # ---------- claim / release ----------

    def claim_job(self, job_id: int, now: datetime) -> bool:
        stale_cutoff = (now - timedelta(hours=1)).isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                """UPDATE scheduled_jobs
                   SET running_at=?
                   WHERE id=? AND enabled=1
                     AND (running_at IS NULL OR running_at < ?)""",
                (now.isoformat(), job_id, stale_cutoff),
            )
            return cur.rowcount > 0

    def release_job(
        self, job_id: int, *, status: RunStatus, error: str = "",
        consecutive_errors: int | None = None,
        last_run_at: datetime | None = None,
    ) -> bool:
        patch: dict = {
            "running_at": None,
            "last_status": status,
            "last_error": error[:500],
        }
        if consecutive_errors is not None:
            patch["consecutive_errors"] = consecutive_errors
        if last_run_at is not None:
            patch["last_run_at"] = last_run_at
        return self.update_job(job_id, patch)

    # ---------- runs ----------

    def start_run(self, job_id: int, expected_at: datetime) -> int:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO job_runs
                   (job_id, expected_at, started_at, status, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (job_id, expected_at.isoformat(), now_iso,
                 RunStatus.RUNNING.value, now_iso),
            )
            return cur.lastrowid or 0

    def finish_run(
        self, run_id: int, *, status: RunStatus,
        result_text: str = "", error: str = "", error_class: str = "",
        delivery_status: str = "", delivery_error: str = "",
    ) -> bool:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT started_at FROM job_runs WHERE id=?", (run_id,),
            ).fetchone()
            duration_ms = None
            if row and row["started_at"]:
                started = datetime.fromisoformat(row["started_at"])
                duration_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
            cur = conn.execute(
                """UPDATE job_runs
                   SET finished_at=?, duration_ms=?, status=?,
                       result_text=?, error=?, error_class=?,
                       delivery_status=?, delivery_error=?
                   WHERE id=?""",
                (now_iso, duration_ms, status.value,
                 result_text[:8000], error[:500], error_class[:100],
                 delivery_status[:50], delivery_error[:500], run_id),
            )
            return cur.rowcount > 0

    def update_run(
        self, run_id: int, *, delivery_status: str = "",
        delivery_error: str = "", result_text: str = "",
    ) -> bool:
        """Update only the delivery-related columns of a run row.

        Used by JobDelivery after the run has been finished by finish_run().
        Does not touch status / finished_at / duration_ms.
        """
        sets: list[str] = []
        vals: list = []
        if delivery_status:
            sets.append("delivery_status=?")
            vals.append(delivery_status[:50])
        if delivery_error:
            sets.append("delivery_error=?")
            vals.append(delivery_error[:500])
        if result_text:
            sets.append("result_text=?")
            vals.append(result_text[:8000])
        if not sets:
            return False
        vals.append(run_id)
        with self._connect() as conn:
            cur = conn.execute(
                f"UPDATE job_runs SET {', '.join(sets)} WHERE id=?",
                vals,
            )
            return cur.rowcount > 0

    def list_runs(
        self, *, job_id: int | None = None,
        status: RunStatus | None = None, limit: int = 100,
    ) -> list[JobRun]:
        sql = "SELECT * FROM job_runs"
        params: list = []
        clauses: list[str] = []
        if job_id is not None:
            clauses.append("job_id=?")
            params.append(job_id)
        if status is not None:
            clauses.append("status=?")
            params.append(status.value)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            return [_row_to_run(r) for r in conn.execute(sql, params).fetchall()]


_JOB_COLS_STR = ", ".join(_JOB_COLS)
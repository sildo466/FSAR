"""FSAR decision log — per-tool-call tracking for self-evolution.

Records every tool execution with outcome + latency, aggregates into
tool_stats for strategy optimization.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from src.utils.config import get_config
from src.utils.logger import logger


@dataclass
class DecisionRecord:
    """One tool call's decision record."""
    id: int | None
    task_id: str
    session_id: str
    step_no: int
    chosen_tool: str
    alternatives: list[str]
    args_summary: str
    latency_ms: int
    success: bool
    error_class: str
    rating: int | None
    created_at: datetime
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "session_id": self.session_id,
            "step_no": self.step_no,
            "chosen_tool": self.chosen_tool,
            "alternatives": self.alternatives,
            "args_summary": self.args_summary,
            "latency_ms": self.latency_ms,
            "success": self.success,
            "error_class": self.error_class,
            "rating": self.rating,
            "created_at": self.created_at.isoformat(),
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cached_tokens": self.cached_tokens,
        }


class DecisionLog:
    """SQLite persistence for decision_log + tool_stats aggregation."""

    def __init__(self, db_path: str | Path | None = None):
        if db_path is not None:
            self._db_path = Path(db_path)
        else:
            config = get_config()
            # Prefer the new dotkey lookup; fall back to legacy attr when
            # FsarConfig hasn't been rehydrated yet.
            try:
                resolved = config.get("memory.sqlite_path") if hasattr(config, "get") else None
            except Exception:
                resolved = None
            if resolved:
                self._db_path = Path(resolved)
            else:
                self._db_path = Path(getattr(config, "memory_sqlite_path", "data/memory.db"))
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS decision_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    step_no INTEGER NOT NULL,
                    chosen_tool TEXT NOT NULL,
                    alternatives TEXT NOT NULL DEFAULT '[]',
                    args_summary TEXT NOT NULL DEFAULT '',
                    latency_ms INTEGER NOT NULL DEFAULT 0,
                    success INTEGER NOT NULL DEFAULT 1,
                    error_class TEXT NOT NULL DEFAULT '',
                    rating INTEGER,
                    created_at TEXT NOT NULL,
                    prompt_tokens INTEGER NOT NULL DEFAULT 0,
                    completion_tokens INTEGER NOT NULL DEFAULT 0,
                    cached_tokens INTEGER NOT NULL DEFAULT 0
                )
            """)
            existing = {row[1] for row in conn.execute("PRAGMA table_info(decision_log)").fetchall()}
            for ddl, name in [
                ("ALTER TABLE decision_log ADD COLUMN prompt_tokens INTEGER NOT NULL DEFAULT 0", "prompt_tokens"),
                ("ALTER TABLE decision_log ADD COLUMN completion_tokens INTEGER NOT NULL DEFAULT 0", "completion_tokens"),
                ("ALTER TABLE decision_log ADD COLUMN cached_tokens INTEGER NOT NULL DEFAULT 0", "cached_tokens"),
            ]:
                if name not in existing:
                    try:
                        conn.execute(ddl)
                    except Exception:
                        pass
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_decision_task "
                "ON decision_log(task_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_decision_tool "
                "ON decision_log(chosen_tool)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_decision_created "
                "ON decision_log(created_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_decision_provider_created "
                "ON decision_log(chosen_tool, created_at)"
            )
            conn.execute("""
                CREATE VIEW IF NOT EXISTS tool_stats AS
                SELECT
                    chosen_tool AS tool_name,
                    COUNT(*) AS total_uses,
                    SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) AS successes,
                    SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) AS failures,
                    ROUND(
                        100.0 * SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) / COUNT(*),
                        1
                    ) AS success_rate_pct,
                    ROUND(AVG(latency_ms), 1) AS avg_latency_ms,
                    ROUND(AVG(CASE WHEN success = 0 THEN latency_ms END), 1) AS avg_failure_latency_ms
                FROM decision_log
                GROUP BY chosen_tool
            """)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def record(self, *, task_id: str, session_id: str, step_no: int,
               chosen_tool: str, alternatives: list[str] | None = None,
               args_summary: str = "", latency_ms: int = 0,
               success: bool = True, error_class: str = "",
               rating: int | None = None,
               prompt_tokens: int = 0,
               completion_tokens: int = 0,
               cached_tokens: int = 0) -> int:
        """Insert one decision row. Returns new id."""
        now = datetime.now().isoformat()
        with self._connect() as conn:
            cur = conn.execute("""
                INSERT INTO decision_log (
                    task_id, session_id, step_no, chosen_tool,
                    alternatives, args_summary, latency_ms,
                    success, error_class, rating, created_at,
                    prompt_tokens, completion_tokens, cached_tokens
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task_id, session_id, step_no, chosen_tool,
                json.dumps(alternatives or [], ensure_ascii=False),
                args_summary[:500], latency_ms,
                1 if success else 0, error_class[:200], rating, now,
                prompt_tokens, completion_tokens, cached_tokens,
            ))
            conn.commit()
            return cur.lastrowid

    def get_for_task(self, task_id: str) -> list[DecisionRecord]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT id, task_id, session_id, step_no, chosen_tool,
                       alternatives, args_summary, latency_ms,
                       success, error_class, rating, created_at,
                       prompt_tokens, completion_tokens, cached_tokens
                FROM decision_log WHERE task_id = ?
                ORDER BY step_no ASC
            """, (task_id,)).fetchall()
        return [self._row_to_record(r) for r in rows]

    def get_token_totals(self) -> dict[str, int]:
        with self._connect() as conn:
            row = conn.execute("""
                SELECT COALESCE(SUM(prompt_tokens), 0),
                       COALESCE(SUM(completion_tokens), 0),
                       COALESCE(SUM(cached_tokens), 0),
                       COUNT(*)
                FROM decision_log
            """).fetchone()
        return {
            "prompt_tokens": int(row[0] or 0),
            "completion_tokens": int(row[1] or 0),
            "cached_tokens": int(row[2] or 0),
            "total_tokens": int((row[0] or 0) + (row[1] or 0)),
            "rows": int(row[3] or 0),
        }

    def get_recent(self, limit: int = 20) -> list[DecisionRecord]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT id, task_id, session_id, step_no, chosen_tool,
                       alternatives, args_summary, latency_ms,
                       success, error_class, rating, created_at,
                       prompt_tokens, completion_tokens, cached_tokens
                FROM decision_log ORDER BY id DESC LIMIT ?
            """, (limit,)).fetchall()
        return [self._row_to_record(r) for r in rows]

    def get_stats(self, min_uses: int = 3) -> list[dict]:
        """Per-tool aggregate stats. Only tools with >= min_uses calls."""
        with self._connect() as conn:
            cur = conn.execute("""
                SELECT * FROM tool_stats WHERE total_uses >= ?
                ORDER BY total_uses DESC
            """, (min_uses,))
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
        if not rows:
            return []
        return [dict(zip(cols, r)) for r in rows]

    def get_top_failure_modes(self, tool_name: str, limit: int = 3) -> list[str]:
        """Most common error_class for a given tool."""
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT error_class, COUNT(*) as n
                FROM decision_log
                WHERE chosen_tool = ? AND success = 0 AND error_class != ''
                GROUP BY error_class
                ORDER BY n DESC LIMIT ?
            """, (tool_name, limit)).fetchall()
        return [r[0] for r in rows]

    def get_total(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM decision_log").fetchone()[0]

    @staticmethod
    def _row_to_record(row: tuple) -> DecisionRecord:
        return DecisionRecord(
            id=row[0],
            task_id=row[1],
            session_id=row[2],
            step_no=row[3],
            chosen_tool=row[4],
            alternatives=json.loads(row[5] or "[]"),
            args_summary=row[6],
            latency_ms=row[7],
            success=bool(row[8]),
            error_class=row[9],
            rating=row[10],
            created_at=datetime.fromisoformat(row[11]),
            prompt_tokens=row[12] if len(row) > 12 else 0,
            completion_tokens=row[13] if len(row) > 13 else 0,
            cached_tokens=row[14] if len(row) > 14 else 0,
        )


_current_task: ContextVar[tuple[str, str]] = ContextVar(
    "fsar_current_task", default=("", "")
)
_task_steps: dict[str, int] = {}
_task_steps_lock = threading.Lock()


def set_task_context(task_id: str, session_id: str) -> None:
    """Set the current task context used by the @track_decision decorator."""
    _current_task.set((task_id, session_id))
    with _task_steps_lock:
        _task_steps.setdefault(task_id, 0)


def clear_task_context() -> None:
    task_id, _ = _current_task.get()
    _current_task.set(("", ""))
    if task_id:
        with _task_steps_lock:
            _task_steps.pop(task_id, None)


def get_task_context() -> dict[str, Any]:
    task_id, session_id = _current_task.get()
    with _task_steps_lock:
        step_no = _task_steps.get(task_id, 0)
    return {"task_id": task_id, "session_id": session_id, "step_no": step_no}


def next_task_context() -> dict[str, Any]:
    task_id, session_id = _current_task.get()
    if not task_id:
        return {"task_id": "", "session_id": session_id, "step_no": 0}
    with _task_steps_lock:
        step_no = _task_steps.get(task_id, 0) + 1
        _task_steps[task_id] = step_no
    return {"task_id": task_id, "session_id": session_id, "step_no": step_no}


def _classify_error(exc: BaseException) -> str:
    """Map an exception to a short error_class tag for grouping."""
    cls = type(exc).__name__.lower()
    msg = str(exc).lower() if exc else ""
    if "timeout" in cls or "timeout" in msg:
        return "timeout"
    if "permission" in cls or "permission" in msg:
        return "permission_denied"
    if "filenotfound" in cls:
        return "not_found"
    if "value" in cls or "valueerror" in cls:
        return "bad_input"
    if "key" in cls:
        return "missing_key"
    if msg.startswith("error: unknown tool"):
        return "unknown_tool"
    return cls or "unknown"

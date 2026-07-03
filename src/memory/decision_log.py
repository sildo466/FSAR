"""FSAR decision log — per-tool-call tracking for self-evolution.

Records every tool execution with outcome + latency, aggregates into
tool_stats for strategy optimization.
"""

from __future__ import annotations

import json
import sqlite3
import time
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
        }


class DecisionLog:
    """SQLite persistence for decision_log + tool_stats aggregation."""

    def __init__(self, db_path: str | Path | None = None):
        config = get_config()
        self._db_path = Path(db_path or config.memory_sqlite_path)
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
                    created_at TEXT NOT NULL
                )
            """)
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
               rating: int | None = None) -> int:
        """Insert one decision row. Returns new id."""
        now = datetime.now().isoformat()
        with self._connect() as conn:
            cur = conn.execute("""
                INSERT INTO decision_log (
                    task_id, session_id, step_no, chosen_tool,
                    alternatives, args_summary, latency_ms,
                    success, error_class, rating, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task_id, session_id, step_no, chosen_tool,
                json.dumps(alternatives or [], ensure_ascii=False),
                args_summary[:500], latency_ms,
                1 if success else 0, error_class[:200], rating, now,
            ))
            conn.commit()
            return cur.lastrowid

    def get_for_task(self, task_id: str) -> list[DecisionRecord]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT id, task_id, session_id, step_no, chosen_tool,
                       alternatives, args_summary, latency_ms,
                       success, error_class, rating, created_at
                FROM decision_log WHERE task_id = ?
                ORDER BY step_no ASC
            """, (task_id,)).fetchall()
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
        )


_current_task: dict[str, Any] = {
    "task_id": "",
    "session_id": "",
    "step_no": 0,
}


def set_task_context(task_id: str, session_id: str) -> None:
    """Set the current task context used by the @track_decision decorator."""
    _current_task["task_id"] = task_id
    _current_task["session_id"] = session_id
    _current_task["step_no"] = 0


def clear_task_context() -> None:
    _current_task["task_id"] = ""
    _current_task["session_id"] = ""
    _current_task["step_no"] = 0


def get_task_context() -> dict[str, Any]:
    return dict(_current_task)


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
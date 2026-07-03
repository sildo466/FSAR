"""FSAR 用户模型 — 偏好、习惯、画像.

存 SQLite（与 long_term 同 db），分三类:
- preferences: 静态偏好 (editor, terminal, browser 等)
- patterns: 行为模式 (重复任务、时段习惯)
- profile: 复盘生成的用户画像 (随时间演进)
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.utils.config import get_config
from src.utils.logger import logger


@dataclass
class UserPreference:
    key: str
    value: str
    confidence: float = 1.0     # 0-1
    source: str = "explicit"    # explicit | inferred | reflection | system
    updated_at: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "value": self.value,
            "confidence": self.confidence,
            "source": self.source,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class UserModel:
    """用户偏好与画像的持久化存储"""

    def __init__(self, db_path: str | Path | None = None):
        config = get_config()
        self._db_path = Path(db_path or config.memory_sqlite_path)
        self._init_db()

    def _init_db(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS preferences (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    confidence REAL DEFAULT 1.0,
                    source TEXT DEFAULT 'explicit',
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pattern TEXT NOT NULL UNIQUE,
                    evidence TEXT NOT NULL,
                    count INTEGER DEFAULT 1,
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS profile (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    source TEXT DEFAULT 'reflection',
                    generated_at TEXT NOT NULL
                )
            """)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self._db_path))

    # ---------- preferences ----------

    def set_preference(self, key: str, value: str, *,
                       confidence: float = 1.0, source: str = "explicit"):
        """设置偏好（覆盖）。"""
        now = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO preferences (key, value, confidence, source, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value=excluded.value,
                    confidence=excluded.confidence,
                    source=excluded.source,
                    updated_at=excluded.updated_at
            """, (key, value, confidence, source, now))
            conn.commit()

    def get_preference(self, key: str, default: str | None = None) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM preferences WHERE key = ?", (key,)
            ).fetchone()
        return row[0] if row else default

    def get_all_preferences(self) -> dict[str, UserPreference]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT key, value, confidence, source, updated_at FROM preferences"
            ).fetchall()
        out: dict[str, UserPreference] = {}
        for r in rows:
            out[r[0]] = UserPreference(
                key=r[0], value=r[1], confidence=r[2], source=r[3],
                updated_at=datetime.fromisoformat(r[4]) if r[4] else None,
            )
        return out

    # ---------- patterns ----------

    def record_pattern(self, pattern: str, evidence: str):
        """记录一次模式命中（已存在则 count +1, last_seen 更新）."""
        now = datetime.now().isoformat()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM patterns WHERE pattern = ?", (pattern,)
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE patterns SET count = count + 1, last_seen = ?, evidence = ? "
                    "WHERE id = ?",
                    (now, evidence, existing[0]),
                )
            else:
                conn.execute("""
                    INSERT INTO patterns (pattern, evidence, count, first_seen, last_seen)
                    VALUES (?, ?, 1, ?, ?)
                """, (pattern, evidence, now, now))
            conn.commit()

    def get_top_patterns(self, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT pattern, evidence, count, first_seen, last_seen
                FROM patterns ORDER BY count DESC LIMIT ?
            """, (limit,)).fetchall()
        return [
            {
                "pattern": r[0], "evidence": r[1], "count": r[2],
                "first_seen": r[3], "last_seen": r[4],
            }
            for r in rows
        ]

    # ---------- profile (reflections) ----------

    def set_profile(self, key: str, value: str, source: str = "reflection"):
        now = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO profile (key, value, source, generated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value=excluded.value,
                    source=excluded.source,
                    generated_at=excluded.generated_at
            """, (key, value, source, now))
            conn.commit()

    def get_profile(self) -> dict[str, str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT key, value FROM profile").fetchall()
        return {k: v for k, v in rows}

    def delete_profile(self, key: str) -> bool:
        """删除画像条目."""
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM profile WHERE key = ?", (key,))
            conn.commit()
            return cur.rowcount > 0

    def get_profile_text(self) -> str:
        """把所有 profile 拼成一段文本，方便注入 LLM context"""
        prof = self.get_profile()
        if not prof:
            return ""
        return "\n".join(f"- {k}: {v}" for k, v in prof.items())
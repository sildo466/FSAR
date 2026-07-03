"""FSAR 用户反馈系统 — RLHF 风格.

每条 assistant 回复可被用户打分 (1-5) + 可选说明原因。
打分数据用途:
- 强化学习信号: 高分回复模式在 user_model 中加权
- 自我反思素材: 低分回复在 idle reflection 时被分析
- 个性化: 推断用户偏好 (e.g. "用户更倾向简洁回复")
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.utils.config import get_config
from src.utils.logger import logger


@dataclass
class Feedback:
    """一条用户反馈"""
    id: int | None
    message_id: int          # 对应 conversations.id
    session_id: str
    rating: int              # 1-5
    reason: str              # 可选
    created_at: datetime

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "message_id": self.message_id,
            "session_id": self.session_id,
            "rating": self.rating,
            "reason": self.reason,
            "created_at": self.created_at.isoformat(),
        }


class FeedbackStore:
    """评分存储 — 与 long_term 同 db，加 ratings 表"""

    def __init__(self, db_path: str | Path | None = None):
        config = get_config()
        self._db_path = Path(db_path or config.memory_sqlite_path)
        self._init_db()

    def _init_db(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ratings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id INTEGER NOT NULL UNIQUE,
                    session_id TEXT NOT NULL,
                    rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
                    reason TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (message_id) REFERENCES conversations(id) ON DELETE CASCADE
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_ratings_session ON ratings(session_id)"
            )
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def add_or_update_rating(self, message_id: int, session_id: str,
                             rating: int, reason: str = "") -> int:
        """添加或更新一条评分（一条 message 只对应一条评分）。返回 id"""
        if not (1 <= rating <= 5):
            raise ValueError(f"rating must be 1-5, got {rating}")
        now = datetime.now().isoformat()
        with self._connect() as conn:
            cur = conn.execute("""
                INSERT INTO ratings (message_id, session_id, rating, reason, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(message_id) DO UPDATE SET
                    rating=excluded.rating,
                    reason=excluded.reason,
                    created_at=excluded.created_at
            """, (message_id, session_id, rating, reason, now))
            conn.commit()
            return cur.lastrowid

    def get_rating(self, message_id: int) -> Feedback | None:
        with self._connect() as conn:
            row = conn.execute("""
                SELECT id, message_id, session_id, rating, reason, created_at
                FROM ratings WHERE message_id = ?
            """, (message_id,)).fetchone()
        if not row:
            return None
        return Feedback(
            id=row[0], message_id=row[1], session_id=row[2],
            rating=row[3], reason=row[4],
            created_at=datetime.fromisoformat(row[5]),
        )

    def get_low_rated(self, limit: int = 20, max_rating: int = 2) -> list[dict]:
        """拿到所有低分回复 (含原文)，供反思使用"""
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT r.id, r.message_id, r.session_id, r.rating, r.reason,
                       c.content, c.timestamp
                FROM ratings r
                JOIN conversations c ON c.id = r.message_id
                WHERE r.rating <= ?
                ORDER BY r.created_at DESC LIMIT ?
            """, (max_rating, limit)).fetchall()
        return [
            {
                "rating_id": r[0], "message_id": r[1], "session_id": r[2],
                "rating": r[3], "reason": r[4],
                "content": r[5], "timestamp": r[6],
            }
            for r in rows
        ]

    def get_high_rated(self, limit: int = 20, min_rating: int = 4) -> list[dict]:
        """拿到高分回复样本 — 复盘时识别"用户喜欢什么" """
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT r.id, r.message_id, r.session_id, r.rating, r.reason,
                       c.content, c.timestamp
                FROM ratings r
                JOIN conversations c ON c.id = r.message_id
                WHERE r.rating >= ?
                ORDER BY r.created_at DESC LIMIT ?
            """, (min_rating, limit)).fetchall()
        return [
            {
                "rating_id": r[0], "message_id": r[1], "session_id": r[2],
                "rating": r[3], "reason": r[4],
                "content": r[5], "timestamp": r[6],
            }
            for r in rows
        ]

    def get_stats(self) -> dict:
        """评分统计"""
        with self._connect() as conn:
            row = conn.execute("""
                SELECT COUNT(*),
                       AVG(rating),
                       SUM(CASE WHEN rating >= 4 THEN 1 ELSE 0 END),
                       SUM(CASE WHEN rating <= 2 THEN 1 ELSE 0 END)
                FROM ratings
            """).fetchone()
        total, avg, high, low = row
        return {
            "total": total or 0,
            "avg": round(avg, 2) if avg else 0.0,
            "high_count": high or 0,
            "low_count": low or 0,
        }
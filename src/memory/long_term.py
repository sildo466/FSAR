"""FSAR 长期记忆 — SQLite 持久化"""

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from src.utils.config import get_config
from src.utils.logger import logger


@dataclass
class MemoryRecord:
    """记忆记录"""
    id: int | None = None
    session_id: str = ""
    role: str = ""              # "user" / "assistant"
    content: str = ""
    summary: str = ""           # 摘要（可选）
    tags: str = ""              # 逗号分隔的标签
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "role": self.role,
            "content": self.content,
            "summary": self.summary,
            "tags": self.tags,
            "timestamp": self.timestamp.isoformat(),
        }


class LongTermMemory:
    """长期记忆 — SQLite 持久化存储"""

    def __init__(self, db_path: str | Path | None = None):
        config = get_config()
        self._db_path = Path(db_path or config.memory_sqlite_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """初始化数据库表"""
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    summary TEXT DEFAULT '',
                    tags TEXT DEFAULT '',
                    timestamp TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_session ON conversations(session_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp ON conversations(timestamp)
            """)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self._db_path))

    def save_message(self, session_id: str, role: str, content: str,
                     summary: str = "", tags: str = "") -> int:
        """保存一条消息到长期记忆。返回新消息 id。"""
        record = MemoryRecord(
            session_id=session_id,
            role=role,
            content=content,
            summary=summary,
            tags=tags,
            timestamp=datetime.now(),
        )
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO conversations (session_id, role, content, summary, tags, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (record.session_id, record.role, record.content,
                 record.summary, record.tags, record.timestamp.isoformat()),
            )
            conn.commit()
            msg_id = cur.lastrowid
        logger.debug(f"Memory saved: [{role}] id={msg_id} {content[:50]}...")
        return msg_id

    def get_recent(self, limit: int = 20, session_id: str | None = None) -> list[MemoryRecord]:
        """获取最近的记忆"""
        with self._connect() as conn:
            if session_id:
                rows = conn.execute(
                    "SELECT id, session_id, role, content, summary, tags, timestamp "
                    "FROM conversations WHERE session_id = ? ORDER BY timestamp DESC LIMIT ?",
                    (session_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, session_id, role, content, summary, tags, timestamp "
                    "FROM conversations ORDER BY timestamp DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [self._row_to_record(r) for r in reversed(rows)]

    def search(self, query: str, limit: int = 10) -> list[MemoryRecord]:
        """关键词搜索记忆"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, session_id, role, content, summary, tags, timestamp "
                "FROM conversations WHERE content LIKE ? OR summary LIKE ? "
                "ORDER BY timestamp DESC LIMIT ?",
                (f"%{query}%", f"%{query}%", limit),
            ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def get_sessions(self) -> list[str]:
        """获取所有会话 ID"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT session_id FROM conversations ORDER BY timestamp DESC"
            ).fetchall()
        return [r[0] for r in rows]

    def list_sessions_with_count(self, limit: int = 20) -> list[dict]:
        """会话列表 + 元数据 (条数 / 首末时间). 按最后活跃时间倒序."""
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT session_id,
                       COUNT(*) as cnt,
                       MIN(timestamp) as first_ts,
                       MAX(timestamp) as last_ts
                FROM conversations
                GROUP BY session_id
                ORDER BY last_ts DESC
                LIMIT ?
            """, (limit,)).fetchall()
        return [
            {
                "session_id": r[0],
                "count": r[1],
                "first_ts": r[2],
                "last_ts": r[3],
            }
            for r in rows
        ]

    def delete_session(self, session_id: str) -> int:
        """删除某会话的全部消息（评分通过外键 CASCADE 自动删除）."""
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM conversations WHERE session_id = ?",
                (session_id,),
            )
            conn.commit()
            return cur.rowcount

    def clear_all(self) -> int:
        """Delete every message in every session (ratings cascade-delete)."""
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM conversations")
            conn.commit()
            return cur.rowcount

    def export_all(self) -> dict:
        """导出全部会话为 JSON dict."""
        sessions = self.list_sessions_with_count(limit=10**9)
        return {
            "exported_at": datetime.now().isoformat(),
            "total_sessions": len(sessions),
            "sessions": [
                {
                    "session_id": s["session_id"],
                    "count": s["count"],
                    "first_ts": s["first_ts"],
                    "last_ts": s["last_ts"],
                    "messages": [m.to_dict() for m in self.get_session_messages(s["session_id"])],
                }
                for s in sessions
            ],
        }

    def get_session_messages(self, session_id: str) -> list[MemoryRecord]:
        """获取某个会话的所有消息"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, session_id, role, content, summary, tags, timestamp "
                "FROM conversations WHERE session_id = ? ORDER BY timestamp ASC",
                (session_id,),
            ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def get_stats(self) -> dict:
        """获取记忆统计"""
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
            sessions = conn.execute("SELECT COUNT(DISTINCT session_id) FROM conversations").fetchone()[0]
        return {
            "total_messages": total,
            "total_sessions": sessions,
        }

    @staticmethod
    def _row_to_record(row: tuple) -> MemoryRecord:
        return MemoryRecord(
            id=row[0],
            session_id=row[1],
            role=row[2],
            content=row[3],
            summary=row[4],
            tags=row[5],
            timestamp=datetime.fromisoformat(row[6]),
        )

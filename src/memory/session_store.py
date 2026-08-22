"""Per-conversation session metadata store (SQLite)."""

from __future__ import annotations

import importlib
import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from src.utils.logger import logger


@dataclass
class SessionRow:
    id: str
    title: str = ""
    pinned: bool = False
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    message_count: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "pinned": self.pinned,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "message_count": self.message_count,
        }


@dataclass
class MessageRow:
    id: int
    session_id: str
    role: str
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    summary: str = ""
    tags: str = ""

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


class SessionStore:
    """CRUD for sessions + per-session messages.

    Sits alongside LongTermMemory on the same SQLite file. Holds metadata
    (title, pinned, message_count) that long_term does not track."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self._db_path))

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id            TEXT PRIMARY KEY,
                    title         TEXT NOT NULL DEFAULT '',
                    pinned        INTEGER NOT NULL DEFAULT 0,
                    created_at    TEXT NOT NULL,
                    updated_at    TEXT NOT NULL,
                    message_count INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sessions_updated "
                "ON sessions(updated_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sessions_pinned "
                "ON sessions(pinned DESC, updated_at DESC)"
            )
            self._ensure_conversations(conn)
            self._migrate_conversations(conn)
            self._migrate_character_binding(conn)
            self._migrate_context_tokens(conn)
            self._migrate_unlocked_tools(conn)
            social_migration = importlib.import_module(
                "data.migrations.2026_07_17_pl2_7_social"
            )
            social_migration.run(conn)
            conn.commit()

    def _migrate_context_tokens(self, conn: sqlite3.Connection) -> None:
        """Idempotent: add context_tokens column (persisted GUI token gauge)."""
        cols = [r[1] for r in conn.execute("PRAGMA table_info(sessions)").fetchall()]
        if "context_tokens" not in cols:
            conn.execute(
                "ALTER TABLE sessions ADD COLUMN context_tokens INTEGER NOT NULL DEFAULT 0"
            )

    def _migrate_unlocked_tools(self, conn: sqlite3.Connection) -> None:
        """Idempotent: add unlocked_tools column (character-mode tool discovery)."""
        cols = [r[1] for r in conn.execute("PRAGMA table_info(sessions)").fetchall()]
        if "unlocked_tools" not in cols:
            conn.execute("ALTER TABLE sessions ADD COLUMN unlocked_tools TEXT")

    def get_unlocked_tools(self, session_id: str) -> set[str]:
        """Session-permanent character-mode unlocks. Empty set when none stored."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT unlocked_tools FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
        if not row or not row[0]:
            return set()
        try:
            loaded = json.loads(row[0])
            return {str(t) for t in loaded} if isinstance(loaded, list) else set()
        except Exception:
            return set()

    def set_unlocked_tools(self, session_id: str, tools: set[str]) -> None:
        raw = json.dumps(sorted(tools), ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                "UPDATE sessions SET unlocked_tools = ? WHERE id = ?",
                (raw, session_id),
            )
            conn.commit()

    def _migrate_character_binding(self, conn) -> None:
        """Idempotent: add character_card_id column to sessions table."""
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "sessions" not in tables:
            return
        cols = [r[1] for r in conn.execute("PRAGMA table_info(sessions)").fetchall()]
        if "character_card_id" not in cols:
            conn.execute(
                "ALTER TABLE sessions ADD COLUMN character_card_id INTEGER "
                "REFERENCES character_cards(id) ON DELETE SET NULL"
            )

    def set_character(self, session_id: str, card_id: int | None) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE sessions SET character_card_id = ?, updated_at = ? WHERE id = ?",
                (card_id, datetime.now().isoformat(), session_id),
            )
            conn.commit()

    def get_character(self, session_id: str) -> int | None:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT character_card_id FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        return r[0] if r and r[0] is not None else None

    def set_context_tokens(self, session_id: str, used: int) -> None:
        """Persist the conversation's last-reported context size so the GUI
        token gauge survives restarts and conversation switches."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE sessions SET context_tokens = ? WHERE id = ?",
                (int(used or 0), session_id),
            )
            conn.commit()

    def get_context_tokens(self, session_id: str) -> int:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT context_tokens FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        return int(r[0] or 0) if r else 0

    def session_ids_for_character(self, character_id: int) -> list[str]:
        """All conversation ids bound to the given character card."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id FROM sessions WHERE character_card_id = ?",
                (character_id,),
            ).fetchall()
        return [r[0] for r in rows]

    def _migrate_conversations(self, conn: sqlite3.Connection) -> None:
        """Idempotent: add session_fk column + backfill from session_id.

        Tolerates a missing conversations table — LongTermMemory owns it
        and may not have initialized yet. Caller is expected to share the
        same DB file with LongTermMemory in production."""
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "conversations" not in tables:
            return
        cols = [r[1] for r in conn.execute("PRAGMA table_info(conversations)").fetchall()]
        if "session_fk" not in cols:
            conn.execute("ALTER TABLE conversations ADD COLUMN session_fk TEXT")
        conn.execute(
            "UPDATE conversations SET session_fk = session_id "
            "WHERE session_fk IS NULL AND session_id IS NOT NULL"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_conv_fk "
            "ON conversations(session_fk)"
        )

    def _ensure_conversations(self, conn: sqlite3.Connection) -> None:
        """Create conversations table if LongTermMemory has not yet run.

        Schema mirrors what LongTermMemory._init_db produces, so subsequent
        LongTermMemory init is a no-op CREATE TABLE IF NOT EXISTS."""
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                session_fk TEXT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                summary TEXT DEFAULT '',
                tags TEXT DEFAULT '',
                timestamp TEXT NOT NULL
            )
            """
        )

    # ---------- sessions CRUD ----------

    def create(self) -> SessionRow:
        now = datetime.now()
        row = SessionRow(
            id=uuid.uuid4().hex,
            created_at=now,
            updated_at=now,
        )
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sessions (id, title, pinned, created_at, updated_at, message_count) "
                "VALUES (?, ?, 0, ?, ?, 0)",
                (row.id, row.title, row.created_at.isoformat(), row.updated_at.isoformat()),
            )
            conn.commit()
        return row

    def get(self, conversation_id: str) -> SessionRow | None:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT id, title, pinned, created_at, updated_at, message_count "
                "FROM sessions WHERE id = ?",
                (conversation_id,),
            ).fetchone()
        return self._row_to_session(r) if r else None

    def list(self, limit: int = 50) -> list[SessionRow]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, title, pinned, created_at, updated_at, message_count "
                "FROM sessions ORDER BY pinned DESC, updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_session(r) for r in rows]

    def rename(self, conversation_id: str, title: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
                (title.strip(), datetime.now().isoformat(), conversation_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def set_pinned(self, conversation_id: str, pinned: bool) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE sessions SET pinned = ?, updated_at = ? WHERE id = ?",
                (1 if pinned else 0, datetime.now().isoformat(), conversation_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def delete(self, conversation_id: str) -> int:
        with self._connect() as conn:
            tables = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            deleted_msgs = 0
            if "conversations" in tables:
                cur = conn.execute(
                    "DELETE FROM conversations WHERE session_fk = ?",
                    (conversation_id,),
                )
                deleted_msgs = cur.rowcount
            conn.execute("DELETE FROM sessions WHERE id = ?", (conversation_id,))
            conn.commit()
        return deleted_msgs

    def touch(self, conversation_id: str) -> None:
        """Bump updated_at + message_count when a message is appended."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE sessions SET updated_at = ?, message_count = message_count + 1 "
                "WHERE id = ?",
                (datetime.now().isoformat(), conversation_id),
            )
            conn.commit()

    # ---------- messages per conversation ----------

    def append_message(
        self, conversation_id: str, role: str, content: str,
        summary: str = "", tags: str = "",
    ) -> int | None:
        """Insert into conversations table with session_fk set; returns row id."""
        if self.get(conversation_id) is None:
            logger.warning(f"append_message: unknown conversation_id={conversation_id}")
            return None
        with self._connect() as conn:
            self._ensure_conversations(conn)
            cur = conn.execute(
                "INSERT INTO conversations "
                "(session_id, session_fk, role, content, summary, tags, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (conversation_id, conversation_id, role, content, summary, tags,
                 datetime.now().isoformat()),
            )
            conn.commit()
            self.touch(conversation_id)
            return cur.lastrowid

    def delete_messages(self, message_ids: list[int]) -> int:
        """Delete messages by row id and decrement sessions.message_count."""
        if not message_ids:
            return 0
        placeholders = ",".join("?" * len(message_ids))
        with self._connect() as conn:
            counts = conn.execute(
                f"SELECT session_fk, COUNT(*) FROM conversations "
                f"WHERE id IN ({placeholders}) GROUP BY session_fk",
                list(message_ids),
            ).fetchall()
            cur = conn.execute(
                f"DELETE FROM conversations WHERE id IN ({placeholders})",
                list(message_ids),
            )
            deleted = cur.rowcount
            for session_id, n in counts:
                if session_id:
                    conn.execute(
                        "UPDATE sessions SET message_count = MAX(0, message_count - ?) "
                        "WHERE id = ?",
                        (n, session_id),
                    )
            conn.commit()
        return deleted

    def get_recent_messages(
        self, conversation_id: str, limit: int = 10,
    ) -> list[MessageRow]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, session_fk, role, content, summary, tags, timestamp "
                "FROM conversations WHERE session_fk = ? "
                "ORDER BY timestamp DESC LIMIT ?",
                (conversation_id, limit),
            ).fetchall()
        return [self._row_to_message(r) for r in reversed(rows)]

    def get_session_messages(
        self, conversation_id: str, limit: int | None = None,
    ) -> list[MessageRow]:
        with self._connect() as conn:
            if limit:
                rows = conn.execute(
                    "SELECT id, session_fk, role, content, summary, tags, timestamp "
                    "FROM conversations WHERE session_fk = ? "
                    "ORDER BY timestamp ASC LIMIT ?",
                    (conversation_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, session_fk, role, content, summary, tags, timestamp "
                    "FROM conversations WHERE session_fk = ? ORDER BY timestamp ASC",
                    (conversation_id,),
                ).fetchall()
        return [self._row_to_message(r) for r in rows]

    # ---------- helpers ----------

    @staticmethod
    def _row_to_session(r: tuple) -> SessionRow:
        return SessionRow(
            id=r[0],
            title=r[1] or "",
            pinned=bool(r[2]),
            created_at=datetime.fromisoformat(r[3]),
            updated_at=datetime.fromisoformat(r[4]),
            message_count=int(r[5] or 0),
        )

    @staticmethod
    def _row_to_message(r: tuple) -> MessageRow:
        return MessageRow(
            id=r[0],
            session_id=r[1],
            role=r[2],
            content=r[3],
            summary=r[4] or "",
            tags=r[5] or "",
            timestamp=datetime.fromisoformat(r[6]),
        )

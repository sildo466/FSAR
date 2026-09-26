# SPDX-License-Identifier: MIT
"""Unified notification store.

One table backs every notification the GUI shows. Producers insert rows;
the quarantine table stays the source of truth for review items, so clearing
notifications never destroys recoverable content.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

NOTIFICATIONS_TABLE = "notifications"
KINDS = ("review", "release", "announcement")


class NotificationStore:
    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {NOTIFICATIONS_TABLE} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL DEFAULT '',
                    ref TEXT,
                    url TEXT,
                    payload_json TEXT,
                    read INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                f"CREATE UNIQUE INDEX IF NOT EXISTS idx_notif_kind_ref "
                f"ON {NOTIFICATIONS_TABLE}(kind, ref)"
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_notif_unread "
                f"ON {NOTIFICATIONS_TABLE}(read, created_at DESC)"
            )
            conn.commit()

    def add(
        self,
        *,
        kind: str,
        title: str,
        body: str = "",
        ref: str | None = None,
        url: str | None = None,
        payload: dict | None = None,
        created_at: str | None = None,
    ) -> int | None:
        """Insert a notification. Returns None when (kind, ref) already exists."""
        if kind not in KINDS:
            raise ValueError(f"unknown notification kind: {kind}")
        with self._connect() as conn:
            cur = conn.execute(
                f"""
                INSERT OR IGNORE INTO {NOTIFICATIONS_TABLE}
                (kind, title, body, ref, url, payload_json, read, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (
                    kind,
                    title,
                    body,
                    None if ref is None else str(ref),
                    url,
                    json.dumps(payload, ensure_ascii=False) if payload else None,
                    created_at or datetime.now().isoformat(timespec="seconds"),
                ),
            )
            conn.commit()
            if cur.rowcount == 0:
                return None
            return int(cur.lastrowid)

    def list(
        self,
        *,
        kind: str | None = None,
        unread_only: bool = False,
        limit: int = 200,
    ) -> list[dict]:
        clauses: list[str] = []
        params: list[object] = []
        if kind is not None:
            clauses.append("kind = ?")
            params.append(kind)
        if unread_only:
            clauses.append("read = 0")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM {NOTIFICATIONS_TABLE} {where} "
                f"ORDER BY created_at DESC, id DESC LIMIT ?",
                params,
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def unread_count(self) -> int:
        with self._connect() as conn:
            return int(
                conn.execute(
                    f"SELECT COUNT(*) FROM {NOTIFICATIONS_TABLE} WHERE read = 0"
                ).fetchone()[0]
            )

    def unread_ids(self, ids: list[int] | None = None) -> list[int]:
        """Ids currently unread, optionally narrowed to `ids`."""
        clauses = ["read = 0"]
        params: list[object] = []
        if ids is not None:
            if not ids:
                return []
            clauses.append(f"id IN ({','.join('?' * len(ids))})")
            params.extend(ids)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT id FROM {NOTIFICATIONS_TABLE} WHERE {' AND '.join(clauses)}",
                params,
            ).fetchall()
        return [int(row[0]) for row in rows]

    def mark_read(self, ids: list[int] | None = None) -> int:
        with self._connect() as conn:
            if ids is None:
                cur = conn.execute(
                    f"UPDATE {NOTIFICATIONS_TABLE} SET read = 1 WHERE read = 0"
                )
            else:
                if not ids:
                    return 0
                placeholders = ",".join("?" * len(ids))
                cur = conn.execute(
                    f"UPDATE {NOTIFICATIONS_TABLE} SET read = 1 "
                    f"WHERE read = 0 AND id IN ({placeholders})",
                    list(ids),
                )
            conn.commit()
            return cur.rowcount

    def clear(self) -> int:
        """Delete notification rows. Quarantined records are untouched."""
        with self._connect() as conn:
            cur = conn.execute(f"DELETE FROM {NOTIFICATIONS_TABLE}")
            conn.commit()
            return cur.rowcount

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        out = dict(row)
        raw = out.pop("payload_json", None)
        out["payload"] = json.loads(raw) if raw else None
        return out

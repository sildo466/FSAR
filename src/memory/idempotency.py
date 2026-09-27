# SPDX-License-Identifier: MIT
"""Request de-duplication for the LAN POSTs.

A member on flaky wifi will retry. Without this, one timeout leaves two
identical lines in the room and wakes the character chain twice. Same key and
same body replays the first answer; same key with a different body is a
conflict, because that is either a caller bug or an attempt to smuggle a
second action under a reused key.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

DEFAULT_TTL_SECONDS = 24 * 3600


class IdempotencyStore:
    def __init__(
        self, db_path: str | Path, *, ttl_seconds: float = DEFAULT_TTL_SECONDS,
    ) -> None:
        self.db_path = str(db_path)
        self.ttl_seconds = float(ttl_seconds)
        with self._connect() as conn:
            self._ensure_tables(conn)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_tables(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lan_idempotency (
                scope        TEXT NOT NULL,
                key          TEXT NOT NULL,
                request_hash TEXT NOT NULL,
                status       INTEGER NOT NULL,
                body         TEXT NOT NULL,
                created_at   REAL NOT NULL,
                PRIMARY KEY (scope, key)
            )
            """
        )
        conn.commit()

    def lookup(
        self, scope: str, key: str, request_hash: str, *,
        now: float | None = None,
    ) -> tuple[str, dict | None]:
        """("new", None) / ("replay", body) / ("conflict", None)."""
        current = time.time() if now is None else now
        with self._connect() as conn:
            row = conn.execute(
                "SELECT request_hash, body, created_at FROM lan_idempotency "
                "WHERE scope = ? AND key = ?",
                (scope, key),
            ).fetchone()
        if row is None:
            return "new", None
        if current - float(row["created_at"]) > self.ttl_seconds:
            return "new", None
        if str(row["request_hash"]) != request_hash:
            return "conflict", None
        try:
            return "replay", json.loads(row["body"])
        except json.JSONDecodeError:
            return "new", None

    def remember(
        self, scope: str, key: str, request_hash: str, status: int, body: dict,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO lan_idempotency "
                "(scope, key, request_hash, status, body, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (scope, key, request_hash, int(status),
                 json.dumps(body, ensure_ascii=False), time.time()),
            )
            conn.commit()

    def purge_expired(self, now: float | None = None) -> int:
        current = time.time() if now is None else now
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM lan_idempotency WHERE created_at < ?",
                (current - self.ttl_seconds,),
            )
            conn.commit()
        return cur.rowcount

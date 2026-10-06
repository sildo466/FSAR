# SPDX-License-Identifier: MIT
"""Addresses that may not reach the LAN listener at all.

Global rather than per room: an address is a network-level actor, and a
blocked one would simply walk into the next room. This is a coarse control and
says so — a machine that changes address walks straight past it.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path


class LanBlocklist:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        with self._connect() as conn:
            self._ensure_tables(conn)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_tables(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lan_blocked_ips (
                ip         TEXT PRIMARY KEY,
                reason     TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()

    def is_blocked(self, ip: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM lan_blocked_ips WHERE ip = ?", (str(ip),),
            ).fetchone()
        return row is not None

    def add(self, ip: str, *, reason: str = "") -> bool:
        cleaned = str(ip).strip()
        if not cleaned:
            raise ValueError("address must not be empty")
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO lan_blocked_ips (ip, reason, created_at) "
                "VALUES (?, ?, ?)",
                (cleaned, reason, datetime.now().isoformat(timespec="seconds")),
            )
            conn.commit()
        return cur.rowcount > 0

    def remove(self, ip: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM lan_blocked_ips WHERE ip = ?", (str(ip).strip(),),
            )
            conn.commit()
        return cur.rowcount > 0

    def list(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                # created_at has second resolution, so two blocks in the same
                # second would otherwise fall back to address order and the
                # "newest first" promise would quietly be wrong.
                "SELECT * FROM lan_blocked_ips "
                "ORDER BY created_at DESC, rowid DESC"
            ).fetchall()
        return [dict(row) for row in rows]

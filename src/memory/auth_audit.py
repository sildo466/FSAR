# SPDX-License-Identifier: MIT
"""Append-only identity audit for the LAN surface.

Kept apart from sandbox_audit on purpose: that one records what a tool tried to
do (path, command, verdict); this one records who got in (credential, source
address, action, outcome). Reading either is hopeless if they are mixed.

Never write a token, a private key, an Authorization header or message text
here. The refusal reasons are precise so an incident stays diagnosable — the
HTTP response is not.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ACTIONS = (
    "token_issued",
    "token_revoked",
    "token_rebound",
    "lan_auth",
    "lan_message",
    "lan_read",
    "lan_doc",
    "ip_blocked",
    "ip_unblocked",
    "lan_paused",
)

RESULTS = ("allow", "deny")


@dataclass
class AuthEvent:
    seq: int
    created_at: str
    action: str
    result: str
    reason: str
    room_id: int | None = None
    member_ref: str | None = None
    token_id: int | None = None
    source_ip: str | None = None
    request_id: str | None = None
    detail: str = ""


class AuthAuditStore:
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
            CREATE TABLE IF NOT EXISTS auth_audit (
                seq        INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                action     TEXT NOT NULL,
                result     TEXT NOT NULL,
                reason     TEXT NOT NULL,
                room_id    INTEGER,
                member_ref TEXT,
                token_id   INTEGER,
                source_ip  TEXT,
                request_id TEXT,
                detail     TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_auth_audit_created "
            "ON auth_audit(created_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_auth_audit_room "
            "ON auth_audit(room_id, created_at DESC)"
        )
        conn.commit()

    def append(
        self,
        *,
        action: str,
        result: str,
        reason: str,
        room_id: int | None = None,
        member_ref: str | None = None,
        token_id: int | None = None,
        source_ip: str | None = None,
        request_id: str | None = None,
        detail: str = "",
    ) -> int:
        if action not in ACTIONS:
            raise ValueError(f"unknown auth audit action: {action}")
        if result not in RESULTS:
            raise ValueError(f"unknown auth audit result: {result}")
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO auth_audit "
                "(created_at, action, result, reason, room_id, member_ref, "
                "token_id, source_ip, request_id, detail) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    datetime.now().isoformat(timespec="seconds"), action, result,
                    reason, room_id, member_ref, token_id, source_ip,
                    request_id, detail,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def list(self, limit: int = 100, room_id: int | None = None) -> list[dict]:
        with self._connect() as conn:
            if room_id is None:
                rows = conn.execute(
                    "SELECT * FROM auth_audit ORDER BY seq DESC LIMIT ?",
                    (max(1, int(limit)),),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM auth_audit WHERE room_id = ? "
                    "ORDER BY seq DESC LIMIT ?",
                    (int(room_id), max(1, int(limit))),
                ).fetchall()
        return [dict(row) for row in rows]

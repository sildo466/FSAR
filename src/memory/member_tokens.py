# SPDX-License-Identifier: MIT
"""Credentials for room members that are not the local user.

Deliberately separate from src/security/ws_auth.py: that one keeps the GUI
token in plaintext on disk (fine for a loopback-only secret) and the two
must never be interchangeable. Here the plaintext is returned exactly once
at issue time and only its sha256 is persisted. The token is 48 bytes of
randomness, not a low-entropy password, so an unsalted digest is a sound
lookup key — do not copy this pattern for user passwords.
"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass
class IssuedToken:
    token_id: int
    token: str
    room_id: int
    member_ref: str


class MemberTokenStore:
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
            CREATE TABLE IF NOT EXISTS room_member_tokens (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                token_hash   TEXT NOT NULL UNIQUE,
                room_id      INTEGER NOT NULL,
                member_ref   TEXT NOT NULL,
                label        TEXT NOT NULL DEFAULT '',
                created_at   TEXT NOT NULL,
                last_used_at TEXT,
                revoked_at   TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_member_tokens_member "
            "ON room_member_tokens(room_id, member_ref)"
        )
        conn.commit()

    def issue(
        self, room_id: int, member_ref: str, *, label: str = "",
    ) -> IssuedToken:
        token = secrets.token_urlsafe(48)
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO room_member_tokens "
                "(token_hash, room_id, member_ref, label, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (_digest(token), room_id, member_ref, label, _now()),
            )
            conn.commit()
            token_id = int(cur.lastrowid)
        return IssuedToken(
            token_id=token_id, token=token,
            room_id=room_id, member_ref=member_ref,
        )

    def resolve(self, token: str) -> tuple[int, str] | None:
        if not token:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, room_id, member_ref, revoked_at "
                "FROM room_member_tokens WHERE token_hash = ?",
                (_digest(token),),
            ).fetchone()
            if row is None or row["revoked_at"] is not None:
                return None
            conn.execute(
                "UPDATE room_member_tokens SET last_used_at = ? WHERE id = ?",
                (_now(), row["id"]),
            )
            conn.commit()
        return int(row["room_id"]), str(row["member_ref"])

    def list_for(self, room_id: int, member_ref: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, label, created_at, last_used_at, revoked_at "
                "FROM room_member_tokens WHERE room_id = ? AND member_ref = ? "
                "ORDER BY created_at ASC",
                (room_id, member_ref),
            ).fetchall()
        return [dict(r) for r in rows]

    def revoke(self, token_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE room_member_tokens SET revoked_at = ? "
                "WHERE id = ? AND revoked_at IS NULL",
                (_now(), token_id),
            )
            conn.commit()
        return cur.rowcount > 0

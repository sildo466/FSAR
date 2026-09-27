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
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_TTL_SECONDS = 7 * 24 * 3600


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
    expires_at: str | None = None


@dataclass
class TokenRecord:
    token_id: int
    room_id: int
    member_ref: str
    label: str
    created_at: str
    expires_at: str | None = None
    revoked_at: str | None = None
    bound_ip: str | None = None
    last_used_at: str | None = None
    last_used_ip: str | None = None


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
        self._migrate_lan_columns(conn)
        conn.commit()

    def _migrate_lan_columns(self, conn: sqlite3.Connection) -> None:
        """Idempotent: expiry and the source-address anchor arrived after P1.

        Existing rows keep NULL in all three, which readers must accept — a
        NULL bound_ip is "the member has never connected yet", not an error.
        """
        cols = [
            r[1] for r in conn.execute(
                "PRAGMA table_info(room_member_tokens)"
            ).fetchall()
        ]
        if "expires_at" not in cols:
            conn.execute("ALTER TABLE room_member_tokens ADD COLUMN expires_at TEXT")
        if "bound_ip" not in cols:
            conn.execute("ALTER TABLE room_member_tokens ADD COLUMN bound_ip TEXT")
        if "last_used_ip" not in cols:
            conn.execute("ALTER TABLE room_member_tokens ADD COLUMN last_used_ip TEXT")

    def issue(
        self, room_id: int, member_ref: str, *, label: str = "",
        ttl_seconds: int | None = DEFAULT_TTL_SECONDS,
    ) -> IssuedToken:
        token = secrets.token_urlsafe(48)
        expires_at = (
            None if ttl_seconds is None
            else (
                datetime.now(timezone.utc) + timedelta(seconds=int(ttl_seconds))
            ).isoformat()
        )
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO room_member_tokens "
                "(token_hash, room_id, member_ref, label, created_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (_digest(token), room_id, member_ref, label, _now(), expires_at),
            )
            conn.commit()
            token_id = int(cur.lastrowid)
        return IssuedToken(
            token_id=token_id, token=token,
            room_id=room_id, member_ref=member_ref, expires_at=expires_at,
        )

    @staticmethod
    def _record_from_row(row: sqlite3.Row) -> TokenRecord:
        return TokenRecord(
            token_id=int(row["id"]),
            room_id=int(row["room_id"]),
            member_ref=str(row["member_ref"]),
            label=str(row["label"] or ""),
            created_at=str(row["created_at"]),
            expires_at=row["expires_at"],
            revoked_at=row["revoked_at"],
            bound_ip=row["bound_ip"],
            last_used_at=row["last_used_at"],
            last_used_ip=row["last_used_ip"],
        )

    def resolve_record(self, token: str) -> TokenRecord | None:
        """The whole row for a token, revoked and expired ones included.

        Whether that is acceptable is the authorization layer's call, and it
        records the exact reason. Filtering here would leave the audit unable
        to tell "revoked" from "expired" from "never existed".
        """
        if not token:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM room_member_tokens WHERE token_hash = ?",
                (_digest(token),),
            ).fetchone()
        return self._record_from_row(row) if row else None

    def resolve(self, token: str) -> tuple[int, str] | None:
        """P1's shape: the identity of a currently usable token, else None.

        No longer records a use — a refused request must not refresh
        last_used_at, so that moved to note_use() and the caller decides.
        """
        record = self.resolve_record(token)
        if record is None or record.revoked_at is not None:
            return None
        if record.expires_at is not None:
            if datetime.fromisoformat(record.expires_at) <= datetime.now(timezone.utc):
                return None
        return record.room_id, record.member_ref

    def bind_ip(self, token_id: int, ip: str) -> bool:
        """First writer wins: the TOFU anchor never moves on its own."""
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE room_member_tokens SET bound_ip = ? "
                "WHERE id = ? AND bound_ip IS NULL",
                (ip, int(token_id)),
            )
            conn.commit()
        return cur.rowcount > 0

    def rebind_ip(self, token_id: int, ip: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE room_member_tokens SET bound_ip = ? WHERE id = ?",
                (ip, int(token_id)),
            )
            conn.commit()
        return cur.rowcount > 0

    def note_use(self, token_id: int, ip: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE room_member_tokens SET last_used_at = ?, last_used_ip = ? "
                "WHERE id = ?",
                (_now(), ip, int(token_id)),
            )
            conn.commit()

    def list_for(self, room_id: int, member_ref: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, label, created_at, last_used_at, revoked_at, "
                "expires_at, bound_ip, last_used_ip "
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

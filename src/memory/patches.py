# SPDX-License-Identifier: MIT
"""Patches waiting to be looked at.

A patch is somebody else's text, so it is kept whole and read only when a
person opens it. The projection a list sends out deliberately leaves the
text behind: what a panel needs first is who sent it and how big it is.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

VALID_STATES = {"pending", "landed", "rejected", "superseded"}


@dataclass
class Patch:
    id: int
    room_id: int
    member_ref: str
    item_key: str | None
    digest: str
    size: int
    state: str
    verdict_reason: str
    decided_by: str | None
    created_at: str
    decided_at: str | None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "room_id": self.room_id,
            "member_ref": self.member_ref,
            "item_key": self.item_key,
            "digest": self.digest,
            "size": self.size,
            "state": self.state,
            "verdict_reason": self.verdict_reason,
            "decided_by": self.decided_by,
            "created_at": self.created_at,
            "decided_at": self.decided_at,
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PatchStore:
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
            CREATE TABLE IF NOT EXISTS room_patches (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id        INTEGER NOT NULL,
                member_ref     TEXT    NOT NULL,
                item_key       TEXT,
                patch_text     TEXT    NOT NULL,
                digest         TEXT    NOT NULL,
                size           INTEGER NOT NULL DEFAULT 0,
                state          TEXT    NOT NULL DEFAULT 'pending',
                verdict_reason TEXT    NOT NULL DEFAULT '',
                decided_by     TEXT,
                created_at     TEXT    NOT NULL,
                decided_at     TEXT,
                UNIQUE (room_id, digest)
            )
            """
        )
        conn.commit()

    @staticmethod
    def _row(r: sqlite3.Row) -> Patch:
        return Patch(
            id=r["id"], room_id=r["room_id"], member_ref=r["member_ref"],
            item_key=r["item_key"], digest=r["digest"], size=int(r["size"] or 0),
            state=r["state"], verdict_reason=r["verdict_reason"] or "",
            decided_by=r["decided_by"], created_at=r["created_at"],
            decided_at=r["decided_at"],
        )

    def add(
        self, room_id: int, member_ref: str, *, patch_text: str, digest: str,
        size: int, item_key: str | None = None,
    ) -> Patch:
        """Queue one patch. The same patch twice is one row, not two.

        The uniqueness is on the digest, so a member that retries an upload
        without an Idempotency-Key still does not stack up copies.
        """
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO room_patches "
                "(room_id, member_ref, item_key, patch_text, digest, size, "
                "state, created_at) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)",
                (int(room_id), str(member_ref), item_key, patch_text,
                 str(digest), int(size), _now()),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM room_patches WHERE room_id = ? AND digest = ?",
                (int(room_id), str(digest)),
            ).fetchone()
        return self._row(row)

    def get(self, room_id: int, patch_id: int) -> Patch | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM room_patches WHERE room_id = ? AND id = ?",
                (int(room_id), int(patch_id)),
            ).fetchone()
        return self._row(row) if row else None

    def text(self, room_id: int, patch_id: int) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT patch_text FROM room_patches WHERE room_id = ? AND id = ?",
                (int(room_id), int(patch_id)),
            ).fetchone()
        return str(row["patch_text"]) if row else None

    def list(self, room_id: int) -> list[Patch]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM room_patches WHERE room_id = ? ORDER BY id ASC",
                (int(room_id),),
            ).fetchall()
        return [self._row(r) for r in rows]

    def pending(self, room_id: int) -> list[Patch]:
        return [p for p in self.list(room_id) if p.state == "pending"]

    def decide(
        self, room_id: int, patch_id: int, state: str, *,
        reason: str = "", decided_by: str = "",
    ) -> Patch | None:
        """Settle a patch once. A patch already settled cannot be settled
        again, so a repeated click cannot land the same change twice."""
        if state not in VALID_STATES:
            raise ValueError(f"invalid patch state '{state}'")
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE room_patches SET state = ?, verdict_reason = ?, "
                "decided_by = ?, decided_at = ? "
                "WHERE room_id = ? AND id = ? AND state = 'pending'",
                (state, reason, decided_by or None, _now(),
                 int(room_id), int(patch_id)),
            )
            conn.commit()
        return self.get(room_id, patch_id) if cur.rowcount else None

    def supersede_pending(self, room_id: int, item_key: str) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE room_patches SET state = 'superseded', decided_at = ? "
                "WHERE room_id = ? AND item_key = ? AND state = 'pending'",
                (_now(), int(room_id), str(item_key)),
            )
            conn.commit()
        return cur.rowcount

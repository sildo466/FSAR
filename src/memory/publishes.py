# SPDX-License-Identifier: MIT
"""What has left the project.

The package itself lives on disk; this table answers only "when did what
leave, and how much of it". One row per publish, and no content: the audit
is about volume and time, not about keeping a second copy of the project.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class PublishRecord:
    id: int
    room_id: int
    member_ref: str
    path_count: int
    bytes: int
    digest: str
    created_at: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "room_id": self.room_id,
            "member_ref": self.member_ref,
            "path_count": self.path_count,
            "bytes": self.bytes,
            "digest": self.digest,
            "created_at": self.created_at,
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PublishStore:
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
            CREATE TABLE IF NOT EXISTS room_publishes (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id    INTEGER NOT NULL,
                member_ref TEXT    NOT NULL,
                path_count INTEGER NOT NULL DEFAULT 0,
                bytes      INTEGER NOT NULL DEFAULT 0,
                digest     TEXT    NOT NULL DEFAULT '',
                created_at TEXT    NOT NULL
            )
            """
        )
        conn.commit()

    @staticmethod
    def _row(r: sqlite3.Row) -> PublishRecord:
        return PublishRecord(
            id=r["id"], room_id=r["room_id"], member_ref=r["member_ref"],
            path_count=int(r["path_count"] or 0), bytes=int(r["bytes"] or 0),
            digest=r["digest"] or "", created_at=r["created_at"],
        )

    def record(
        self, room_id: int, member_ref: str, *,
        path_count: int, byte_count: int, digest: str,
    ) -> PublishRecord:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO room_publishes "
                "(room_id, member_ref, path_count, bytes, digest, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    int(room_id), str(member_ref), int(path_count),
                    int(byte_count), str(digest), _now(),
                ),
            )
            conn.commit()
            row_id = int(cur.lastrowid)
        return self.get(row_id)

    def get(self, publish_id: int) -> PublishRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM room_publishes WHERE id = ?", (int(publish_id),),
            ).fetchone()
        return self._row(row) if row else None

    def list(self, room_id: int) -> list[PublishRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM room_publishes WHERE room_id = ? ORDER BY id ASC",
                (int(room_id),),
            ).fetchall()
        return [self._row(r) for r in rows]

    def latest(self, room_id: int) -> PublishRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM room_publishes WHERE room_id = ? "
                "ORDER BY id DESC LIMIT 1",
                (int(room_id),),
            ).fetchone()
        return self._row(row) if row else None

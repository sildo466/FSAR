# SPDX-License-Identifier: MIT
"""The room's plan board.

One writer: A. Members speak and report; the board is rewritten only through
A, so there is nothing to converge and no distributed ordering to get wrong.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

VALID_STATUS = {"todo", "doing", "blocked", "done"}


@dataclass
class PlanItem:
    id: int
    room_id: int
    item_key: str
    text: str
    owner_kind: str | None
    owner_ref: str | None
    status: str
    lease_expires_at: str | None
    evidence: str
    commit_ref: str | None
    attempts: int
    created_at: str
    updated_at: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "room_id": self.room_id,
            "item_key": self.item_key,
            "text": self.text,
            "owner_kind": self.owner_kind,
            "owner_ref": self.owner_ref,
            "status": self.status,
            "lease_expires_at": self.lease_expires_at,
            "evidence": self.evidence,
            "commit_ref": self.commit_ref,
            "attempts": self.attempts,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RoomPlanStore:
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
            CREATE TABLE IF NOT EXISTS room_plan_items (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id           INTEGER NOT NULL,
                item_key          TEXT    NOT NULL,
                text              TEXT    NOT NULL,
                owner_kind        TEXT,
                owner_ref         TEXT,
                status            TEXT    NOT NULL DEFAULT 'todo',
                lease_expires_at  TEXT,
                evidence          TEXT    NOT NULL DEFAULT '',
                commit_ref        TEXT,
                attempts          INTEGER NOT NULL DEFAULT 0,
                created_at        TEXT    NOT NULL,
                updated_at        TEXT    NOT NULL,
                UNIQUE (room_id, item_key)
            )
            """
        )
        conn.commit()

    @staticmethod
    def _row(r: sqlite3.Row) -> PlanItem:
        return PlanItem(
            id=r["id"], room_id=r["room_id"], item_key=r["item_key"],
            text=r["text"], owner_kind=r["owner_kind"], owner_ref=r["owner_ref"],
            status=r["status"], lease_expires_at=r["lease_expires_at"],
            evidence=r["evidence"] or "", commit_ref=r["commit_ref"],
            attempts=int(r["attempts"] or 0),
            created_at=r["created_at"], updated_at=r["updated_at"],
        )

    def list(self, room_id: int) -> list[PlanItem]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM room_plan_items WHERE room_id = ? ORDER BY id ASC",
                (int(room_id),),
            ).fetchall()
        return [self._row(r) for r in rows]

    def get(self, room_id: int, item_key: str) -> PlanItem | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM room_plan_items WHERE room_id = ? AND item_key = ?",
                (int(room_id), item_key),
            ).fetchone()
        return self._row(row) if row else None

    def replace(self, room_id: int, items: list[dict]) -> list[PlanItem]:
        """Write the whole board.

        The commit ref and the lease belong to A and survive this call: a
        member that could clear them with one plan_write could erase its own
        promotion record or its own lease.
        """
        now = _now()
        with self._connect() as conn:
            keep: list[str] = []
            for raw in items or []:
                key = str(raw.get("id") or "").strip()
                if not key:
                    continue
                keep.append(key)
                owner = raw.get("owner")
                owner = owner if isinstance(owner, dict) else {}
                owner_kind = str(owner.get("kind") or "").strip() or None
                owner_ref = str(owner.get("ref") or "").strip() or None
                status = str(raw.get("status") or "todo")
                if status not in VALID_STATUS:
                    status = "todo"
                conn.execute(
                    """
                    INSERT INTO room_plan_items
                        (room_id, item_key, text, owner_kind, owner_ref, status,
                         evidence, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (room_id, item_key) DO UPDATE SET
                        text = excluded.text,
                        owner_kind = excluded.owner_kind,
                        owner_ref = excluded.owner_ref,
                        status = excluded.status,
                        evidence = excluded.evidence,
                        updated_at = excluded.updated_at
                    """,
                    (
                        int(room_id), key, str(raw.get("text") or ""),
                        owner_kind, owner_ref, status,
                        str(raw.get("evidence") or ""), now, now,
                    ),
                )
            if keep:
                marks = ",".join("?" for _ in keep)
                conn.execute(
                    f"DELETE FROM room_plan_items WHERE room_id = ? "
                    f"AND item_key NOT IN ({marks})",
                    (int(room_id), *keep),
                )
            else:
                conn.execute(
                    "DELETE FROM room_plan_items WHERE room_id = ?", (int(room_id),),
                )
            conn.commit()
        return self.list(room_id)

    def set_status(
        self, room_id: int, item_key: str, status: str, evidence: str = "",
    ) -> PlanItem | None:
        if status not in VALID_STATUS:
            raise ValueError(f"invalid plan status '{status}'")
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE room_plan_items SET status = ?, evidence = ?, updated_at = ? "
                "WHERE room_id = ? AND item_key = ?",
                (status, evidence, _now(), int(room_id), item_key),
            )
            conn.commit()
        return self.get(room_id, item_key) if cur.rowcount else None

    def claim(self, room_id: int, item_key: str, lease_expires_at: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE room_plan_items SET status = 'doing', lease_expires_at = ?, "
                "updated_at = ? WHERE room_id = ? AND item_key = ?",
                (lease_expires_at, _now(), int(room_id), item_key),
            )
            conn.commit()
        return cur.rowcount > 0

    def clear_lease(self, room_id: int, item_key: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE room_plan_items SET lease_expires_at = NULL, updated_at = ? "
                "WHERE room_id = ? AND item_key = ?",
                (_now(), int(room_id), item_key),
            )
            conn.commit()
        return cur.rowcount > 0

    def bump_attempts(self, room_id: int, item_key: str) -> int:
        with self._connect() as conn:
            conn.execute(
                "UPDATE room_plan_items SET attempts = attempts + 1, updated_at = ? "
                "WHERE room_id = ? AND item_key = ?",
                (_now(), int(room_id), item_key),
            )
            conn.commit()
        item = self.get(room_id, item_key)
        return item.attempts if item else 0

    def set_commit_ref(
        self, room_id: int, item_key: str, commit_ref: str,
    ) -> PlanItem | None:
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE room_plan_items SET commit_ref = ?, updated_at = ? "
                "WHERE room_id = ? AND item_key = ?",
                (commit_ref, _now(), int(room_id), item_key),
            )
            conn.commit()
        return self.get(room_id, item_key) if cur.rowcount else None

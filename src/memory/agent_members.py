# SPDX-License-Identifier: MIT
"""External agents as room members.

A separate table from `room_members` on purpose: that one is keyed by
character_card_id and `RoomStore.members()` is relied on by the existing
group chain, speaker naming and history rendering. Agent members carry a
string ref instead and are never character cards.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

VALID_STATES = {"active", "muted"}


@dataclass
class AgentMember:
    room_id: int
    ref: str
    display_name: str
    state: str = "active"
    joined_at: str = ""


class AgentMemberStore:
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
            CREATE TABLE IF NOT EXISTS room_agent_members (
                room_id      INTEGER NOT NULL,
                ref          TEXT NOT NULL,
                display_name TEXT NOT NULL,
                state        TEXT NOT NULL DEFAULT 'active',
                joined_at    TEXT NOT NULL,
                PRIMARY KEY (room_id, ref)
            )
            """
        )
        conn.commit()

    @staticmethod
    def _row(r: sqlite3.Row) -> AgentMember:
        return AgentMember(
            room_id=r["room_id"], ref=r["ref"],
            display_name=r["display_name"], state=r["state"],
            joined_at=r["joined_at"],
        )

    def members(self, room_id: int) -> list[AgentMember]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM room_agent_members WHERE room_id = ? "
                "ORDER BY joined_at ASC, ref ASC",
                (room_id,),
            ).fetchall()
        return [self._row(r) for r in rows]

    def get(self, room_id: int, ref: str) -> AgentMember | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM room_agent_members WHERE room_id = ? AND ref = ?",
                (room_id, ref),
            ).fetchone()
        return self._row(row) if row else None

    def add(self, room_id: int, *, ref: str, display_name: str) -> AgentMember:
        cleaned = ref.strip()
        if not cleaned:
            raise ValueError("member ref must not be empty")
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO room_agent_members "
                "(room_id, ref, display_name, state, joined_at) "
                "VALUES (?, ?, ?, 'active', ?)",
                (room_id, cleaned, display_name.strip(), now),
            )
            conn.commit()
        return AgentMember(
            room_id=room_id, ref=cleaned,
            display_name=display_name.strip(), state="active", joined_at=now,
        )

    def set_state(self, room_id: int, ref: str, state: str) -> bool:
        if state not in VALID_STATES:
            raise ValueError(f"invalid member state '{state}'")
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE room_agent_members SET state = ? "
                "WHERE room_id = ? AND ref = ?",
                (state, room_id, ref),
            )
            conn.commit()
        return cur.rowcount > 0

    def remove(self, room_id: int, ref: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM room_agent_members WHERE room_id = ? AND ref = ?",
                (room_id, ref),
            )
            conn.commit()
        return cur.rowcount > 0

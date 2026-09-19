# SPDX-License-Identifier: MIT
"""Group chat rooms. A room is an entity that owns exactly one session."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.memory.session_store import MessageRow, SessionStore


@dataclass
class Room:
    id: int | None
    name: str
    description: str = ""
    scenario_prompt: str = ""
    session_id: str = ""
    user_card_id: int | None = None
    pinned: bool = False
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "scenario_prompt": self.scenario_prompt,
            "session_id": self.session_id,
            "user_card_id": self.user_card_id,
            "pinned": self.pinned,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class RoomStore:
    """CRUD for rooms plus membership. Rooms own exactly one session."""

    def __init__(self, db_path: str | Path, session_store: SessionStore) -> None:
        self._db = Path(db_path)
        self.session_store = session_store
        self._db.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            self._ensure_tables(conn)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_tables(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rooms (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                name            TEXT NOT NULL,
                description     TEXT NOT NULL DEFAULT '',
                scenario_prompt TEXT NOT NULL DEFAULT '',
                session_id      TEXT NOT NULL,
                user_card_id    INTEGER,
                pinned          INTEGER NOT NULL DEFAULT 0,
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS room_members (
                room_id           INTEGER NOT NULL,
                character_card_id INTEGER NOT NULL
                    REFERENCES character_cards(id) ON DELETE CASCADE,
                joined_at         TEXT NOT NULL,
                PRIMARY KEY (room_id, character_card_id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_room_members_room "
            "ON room_members(room_id)"
        )
        conn.commit()

    @staticmethod
    def _row_to_room(r: sqlite3.Row) -> Room:
        return Room(
            id=r["id"],
            name=r["name"],
            description=r["description"] or "",
            scenario_prompt=r["scenario_prompt"] or "",
            session_id=r["session_id"],
            user_card_id=r["user_card_id"],
            pinned=bool(r["pinned"]),
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )

    def create(
        self,
        *,
        name: str,
        description: str = "",
        scenario_prompt: str = "",
        user_card_id: int | None = None,
        character_ids: list[int],
    ) -> Room:
        now = datetime.now().isoformat()
        session = self.session_store.create(kind="group")
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO rooms "
                "(name, description, scenario_prompt, session_id, user_card_id, "
                "pinned, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, 0, ?, ?)",
                (name, description, scenario_prompt, session.id,
                 user_card_id, now, now),
            )
            room_id = cur.lastrowid
            for cid in character_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO room_members "
                    "(room_id, character_card_id, joined_at) VALUES (?, ?, ?)",
                    (room_id, int(cid), now),
                )
            conn.commit()
        room = self.get(room_id)
        assert room is not None
        return room

    def get(self, room_id: int) -> Room | None:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT * FROM rooms WHERE id = ?", (room_id,)
            ).fetchone()
        return self._row_to_room(r) if r else None

    def list(self) -> list[Room]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM rooms ORDER BY pinned DESC, updated_at DESC"
            ).fetchall()
        return [self._row_to_room(r) for r in rows]

    def update(
        self,
        room_id: int,
        *,
        name: str | None = None,
        description: str | None = None,
        scenario_prompt: str | None = None,
        user_card_id: int | None = None,
        pinned: bool | None = None,
    ) -> Room | None:
        current = self.get(room_id)
        if current is None:
            return None
        with self._connect() as conn:
            conn.execute(
                "UPDATE rooms SET name = ?, description = ?, scenario_prompt = ?, "
                "user_card_id = ?, pinned = ?, updated_at = ? WHERE id = ?",
                (
                    current.name if name is None else name,
                    current.description if description is None else description,
                    current.scenario_prompt if scenario_prompt is None else scenario_prompt,
                    current.user_card_id if user_card_id is None else user_card_id,
                    int(current.pinned if pinned is None else pinned),
                    datetime.now().isoformat(),
                    room_id,
                ),
            )
            conn.commit()
        return self.get(room_id)

    def touch(self, room_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE rooms SET updated_at = ? WHERE id = ?",
                (datetime.now().isoformat(), room_id),
            )
            conn.commit()

    def delete(self, room_id: int) -> bool:
        room = self.get(room_id)
        if room is None:
            return False
        with self._connect() as conn:
            conn.execute("DELETE FROM room_members WHERE room_id = ?", (room_id,))
            cur = conn.execute("DELETE FROM rooms WHERE id = ?", (room_id,))
            conn.commit()
        self.session_store.delete(room.session_id)
        return cur.rowcount > 0

    def members(self, room_id: int) -> list[int]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT character_card_id FROM room_members "
                "WHERE room_id = ? ORDER BY joined_at ASC, character_card_id ASC",
                (room_id,),
            ).fetchall()
        return [int(r[0]) for r in rows]

    def add_members(self, room_id: int, character_ids: list[int]) -> None:
        now = datetime.now().isoformat()
        with self._connect() as conn:
            for cid in character_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO room_members "
                    "(room_id, character_card_id, joined_at) VALUES (?, ?, ?)",
                    (room_id, int(cid), now),
                )
            conn.execute(
                "UPDATE rooms SET updated_at = ? WHERE id = ?",
                (now, room_id),
            )
            conn.commit()

    def remove_member(self, room_id: int, character_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM room_members WHERE room_id = ? AND character_card_id = ?",
                (room_id, character_id),
            )
            conn.commit()
        return cur.rowcount > 0

    def prune_missing_members(self) -> int:
        """Drop member rows whose character card no longer exists.

        The schema declares ON DELETE CASCADE, but SQLite only enforces foreign
        keys per connection and this codebase never enables the pragma, so the
        cascade never fires. Prune explicitly instead of pretending it works."""
        with self._connect() as conn:
            tables = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            if "character_cards" not in tables:
                return 0
            cur = conn.execute(
                "DELETE FROM room_members WHERE character_card_id NOT IN "
                "(SELECT id FROM character_cards)"
            )
            conn.commit()
            return cur.rowcount

    def messages_with_speaker(self, room_id: int) -> list[MessageRow]:
        room = self.get(room_id)
        if room is None:
            return []
        return self.session_store.get_session_messages(room.session_id)

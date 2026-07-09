# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import datetime as _dt
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CharacterCard:
    id: int | None
    name: str
    description: str
    personality: str
    scenario: str = ""
    system_prompt_override: str = ""
    example_dialogues: list[dict] | None = None
    tags: list[str] | None = None
    avatar_path: str | None = None
    is_default: int = 0
    created_by: str = "user"
    created_at: str = ""
    updated_at: str = ""
    emotion_state: dict[str, float] | None = None
    emotion_schema: list[dict] | None = None
    emotion_formulas: dict[str, str] | None = None


@dataclass
class UserCard:
    id: int | None
    name: str
    description: str
    preferences: dict | None = None
    interests: list[str] | None = None
    communication_style: str = ""
    avatar_path: str | None = None
    is_default: int = 0
    created_by: str = "user"
    created_at: str = ""
    updated_at: str = ""


class CardRepo:
    def __init__(self, db_path: Path):
        self._db = db_path

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db)

    def ensure_tables(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS character_cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                avatar_path TEXT,
                description TEXT NOT NULL,
                personality TEXT NOT NULL,
                scenario TEXT DEFAULT '',
                system_prompt_override TEXT DEFAULT '',
                example_dialogues TEXT DEFAULT '[]',
                tags TEXT DEFAULT '[]',
                is_default INTEGER NOT NULL DEFAULT 0,
                created_by TEXT NOT NULL DEFAULT 'user',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                emotion_state TEXT DEFAULT '{}',
                emotion_schema TEXT DEFAULT '[]',
                emotion_formulas TEXT DEFAULT '{}'
            )
            """
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_character_cards_default "
            "ON character_cards(is_default) WHERE is_default = 1"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                avatar_path TEXT,
                description TEXT NOT NULL,
                preferences TEXT DEFAULT '{}',
                interests TEXT DEFAULT '[]',
                communication_style TEXT DEFAULT '',
                is_default INTEGER NOT NULL DEFAULT 0,
                created_by TEXT NOT NULL DEFAULT 'user',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_user_cards_default "
            "ON user_cards(is_default) WHERE is_default = 1"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS emotion_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                character_id INTEGER NOT NULL,
                session_id TEXT,
                metric_key TEXT NOT NULL,
                old_value REAL NOT NULL,
                new_value REAL NOT NULL,
                delta REAL NOT NULL,
                reason TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'update_emotion',
                created_at TEXT NOT NULL,
                FOREIGN KEY (character_id) REFERENCES character_cards(id) ON DELETE CASCADE
            )
            """
        )
        conn.commit()

    def _row_to_character(self, row: sqlite3.Row) -> CharacterCard:
        return CharacterCard(
            id=row["id"],
            name=row["name"],
            avatar_path=row["avatar_path"],
            description=row["description"],
            personality=row["personality"],
            scenario=row["scenario"],
            system_prompt_override=row["system_prompt_override"],
            example_dialogues=json.loads(row["example_dialogues"] or "[]"),
            tags=json.loads(row["tags"] or "[]"),
            is_default=row["is_default"],
            created_by=row["created_by"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            emotion_state=json.loads(row["emotion_state"] or "{}"),
            emotion_schema=json.loads(row["emotion_schema"] or "[]"),
            emotion_formulas=json.loads(row["emotion_formulas"] or "{}"),
        )

    def list_characters(self) -> list[CharacterCard]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM character_cards ORDER BY is_default DESC, name ASC"
            ).fetchall()
        return [self._row_to_character(r) for r in rows]

    def get_character(self, card_id: int) -> CharacterCard | None:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            r = conn.execute(
                "SELECT * FROM character_cards WHERE id = ?", (card_id,)
            ).fetchone()
        return self._row_to_character(r) if r else None

    def get_default_character(self) -> CharacterCard | None:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            r = conn.execute(
                "SELECT * FROM character_cards WHERE is_default = 1 LIMIT 1"
            ).fetchone()
        return self._row_to_character(r) if r else None

    def upsert_character(self, card: CharacterCard) -> int:
        now = _dt.datetime.now().isoformat()
        payload = (
            card.name,
            card.avatar_path,
            card.description,
            card.personality,
            card.scenario,
            card.system_prompt_override,
            json.dumps(card.example_dialogues or [], ensure_ascii=False),
            json.dumps(card.tags or [], ensure_ascii=False),
            card.is_default,
            card.created_by,
            card.created_at or now,
            card.updated_at or now,
            json.dumps(card.emotion_state or {}, ensure_ascii=False),
            json.dumps(card.emotion_schema or [], ensure_ascii=False),
            json.dumps(card.emotion_formulas or {}, ensure_ascii=False),
        )
        with self._connect() as conn:
            if card.id is None:
                cur = conn.execute(
                    """
                    INSERT INTO character_cards
                    (name, avatar_path, description, personality, scenario,
                     system_prompt_override, example_dialogues, tags, is_default,
                     created_by, created_at, updated_at,
                     emotion_state, emotion_schema, emotion_formulas)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    payload,
                )
                return cur.lastrowid
            else:
                conn.execute(
                    """
                    UPDATE character_cards SET
                        name=?, avatar_path=?, description=?, personality=?,
                        scenario=?, system_prompt_override=?,
                        example_dialogues=?, tags=?, is_default=?, created_by=?,
                        created_at=?, updated_at=?,
                        emotion_state=?, emotion_schema=?, emotion_formulas=?
                    WHERE id=?
                    """,
                    payload + (card.id,),
                )
                return card.id

    def delete_character(self, card_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM character_cards WHERE id = ?", (card_id,)
            )
            return cur.rowcount > 0

    def set_default_character(self, card_id: int) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE character_cards SET is_default = 0 WHERE is_default = 1")
            conn.execute("UPDATE character_cards SET is_default = 1 WHERE id = ?", (card_id,))
            conn.commit()

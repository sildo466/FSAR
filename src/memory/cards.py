# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

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
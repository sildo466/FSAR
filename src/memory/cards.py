# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import datetime as _dt
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

DEFAULT_EMOTION_PATH = Path(__file__).parent.parent.parent / "data" / "emotion_default.json"


def _load_default_emotion() -> tuple[list[dict], dict[str, str]]:
    data = json.loads(DEFAULT_EMOTION_PATH.read_text(encoding="utf-8"))
    return data["schema"], data["formulas"]


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
        self._default_schema, self._default_formulas = _load_default_emotion()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db)

    def apply_default_emotion(self, card: CharacterCard) -> CharacterCard:
        if not card.emotion_state:
            card.emotion_state = {m["key"]: float(m["initial"]) for m in self._default_schema}
        if not card.emotion_schema:
            card.emotion_schema = list(self._default_schema)
        if not card.emotion_formulas:
            card.emotion_formulas = dict(self._default_formulas)
        return card

    def get_emotion_state(self, character_id: int) -> dict[str, float]:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT emotion_state FROM character_cards WHERE id = ?",
                (character_id,),
            ).fetchone()
        if not r:
            return {}
        return json.loads(r[0] or "{}")

    def set_emotion_state(self, character_id: int, state: dict[str, float]) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE character_cards SET emotion_state = ?, updated_at = ? WHERE id = ?",
                (json.dumps(state, ensure_ascii=False),
                 _dt.datetime.now().isoformat(), character_id),
            )
            conn.commit()

    def get_emotion_schema(self, character_id: int) -> list[dict]:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT emotion_schema FROM character_cards WHERE id = ?",
                (character_id,),
            ).fetchone()
        return json.loads(r[0] or "[]") if r else []

    def get_emotion_formulas(self, character_id: int) -> dict[str, str]:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT emotion_formulas FROM character_cards WHERE id = ?",
                (character_id,),
            ).fetchone()
        return json.loads(r[0] or "{}") if r else {}

    def set_emotion_schema_and_formulas(
        self, character_id: int, schema: list[dict], formulas: dict[str, str]
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE character_cards SET emotion_schema = ?, emotion_formulas = ?, "
                "updated_at = ? WHERE id = ?",
                (json.dumps(schema, ensure_ascii=False),
                 json.dumps(formulas, ensure_ascii=False),
                 _dt.datetime.now().isoformat(), character_id),
            )
            conn.commit()

    def append_emotion_audit(
        self,
        character_id: int,
        session_id: str | None,
        metric_key: str,
        old_value: float,
        new_value: float,
        reason: str,
        source: str = "update_emotion",
    ) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO emotion_audit
                (character_id, session_id, metric_key, old_value, new_value,
                 delta, reason, source, created_at)
                VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (character_id, session_id, metric_key, old_value, new_value,
                 new_value - old_value, reason, source,
                 _dt.datetime.now().isoformat()),
            )
            conn.commit()
            return cur.lastrowid

    def save_avatar(self, card_id: int, ext: str, data: bytes) -> str:
        avatars_dir = self._db.parent / "avatars"
        avatars_dir.mkdir(parents=True, exist_ok=True)
        path = avatars_dir / f"{card_id}.{ext}"
        path.write_bytes(data)
        rel = f"avatars/{card_id}.{ext}"
        with self._connect() as conn:
            conn.execute(
                "UPDATE character_cards SET avatar_path = ?, updated_at = ? WHERE id = ?",
                (rel, _dt.datetime.now().isoformat(), card_id),
            )
            conn.commit()
        return rel

    def seed_builtins_if_empty(self) -> int:
        """Insert built-in cards from data/cards/*.json if tables are empty."""
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT COUNT(*) FROM character_cards"
            ).fetchone()[0]
            if existing > 0:
                return 0
        cards_dir = DEFAULT_EMOTION_PATH.parent / "cards"
        if not cards_dir.exists():
            return 0
        seeded = 0
        is_default_set = False
        for json_path in sorted(cards_dir.glob("*.json")):
            if json_path.name == "_meta.json":
                continue
            data = json.loads(json_path.read_text(encoding="utf-8"))
            meta = data.pop("_meta", {})
            if data.get("name") == "default-user":
                self.upsert_user_card(UserCard(
                    id=None, name=data["name"],
                    description=data.get("description", ""),
                    preferences=data.get("preferences", {}),
                    interests=data.get("interests", []),
                    communication_style=data.get("communication_style", ""),
                    is_default=1,
                    created_by=meta.get("created_by", "builtin"),
                    created_at="", updated_at="",
                ))
            else:
                is_default = 0
                if not is_default_set and meta.get("role") == "FSAR" and data.get("language") == "zh":
                    is_default = 1
                    is_default_set = True
                self.upsert_character(CharacterCard(
                    id=None, name=data["name"],
                    description=data["description"],
                    personality=data["personality"],
                    scenario=data.get("scenario", ""),
                    system_prompt_override=data.get("system_prompt_override", ""),
                    example_dialogues=data.get("example_dialogues", []),
                    tags=data.get("tags", []),
                    is_default=is_default,
                    created_by=meta.get("created_by", "builtin"),
                    created_at="", updated_at="",
                ))
                seeded += 1
        return seeded

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
        card = self.apply_default_emotion(card)
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

    def _row_to_user(self, row: sqlite3.Row) -> UserCard:
        return UserCard(
            id=row["id"],
            name=row["name"],
            avatar_path=row["avatar_path"],
            description=row["description"],
            preferences=json.loads(row["preferences"] or "{}"),
            interests=json.loads(row["interests"] or "[]"),
            communication_style=row["communication_style"],
            is_default=row["is_default"],
            created_by=row["created_by"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def list_user_cards(self) -> list[UserCard]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM user_cards ORDER BY is_default DESC, name ASC"
            ).fetchall()
        return [self._row_to_user(r) for r in rows]

    def get_user_card(self, card_id: int) -> UserCard | None:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            r = conn.execute("SELECT * FROM user_cards WHERE id = ?", (card_id,)).fetchone()
        return self._row_to_user(r) if r else None

    def get_default_user_card(self) -> UserCard | None:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            r = conn.execute("SELECT * FROM user_cards WHERE is_default = 1 LIMIT 1").fetchone()
        return self._row_to_user(r) if r else None

    def upsert_user_card(self, card: UserCard) -> int:
        now = _dt.datetime.now().isoformat()
        payload = (
            card.name, card.avatar_path, card.description,
            json.dumps(card.preferences or {}, ensure_ascii=False),
            json.dumps(card.interests or [], ensure_ascii=False),
            card.communication_style, card.is_default, card.created_by,
            card.created_at or now, card.updated_at or now,
        )
        with self._connect() as conn:
            if card.id is None:
                cur = conn.execute(
                    """
                    INSERT INTO user_cards
                    (name, avatar_path, description, preferences, interests,
                     communication_style, is_default, created_by, created_at, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?)
                    """,
                    payload,
                )
                return cur.lastrowid
            else:
                conn.execute(
                    """
                    UPDATE user_cards SET
                        name=?, avatar_path=?, description=?, preferences=?,
                        interests=?, communication_style=?, is_default=?,
                        created_by=?, created_at=?, updated_at=?
                    WHERE id=?
                    """,
                    payload + (card.id,),
                )
                return card.id

    def delete_user_card(self, card_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM user_cards WHERE id = ?", (card_id,))
            return cur.rowcount > 0

    def set_default_user_card(self, card_id: int) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE user_cards SET is_default = 0 WHERE is_default = 1")
            conn.execute("UPDATE user_cards SET is_default = 1 WHERE id = ?", (card_id,))
            conn.commit()

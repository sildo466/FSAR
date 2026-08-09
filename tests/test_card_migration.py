# SPDX-License-Identifier: MIT
"""Character-card TTS field migration tests."""

import sqlite3

from src.memory.cards import CardRepo, CharacterCard


def create_legacy_schema(path):
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE character_cards (
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


def columns(path):
    with sqlite3.connect(path) as connection:
        return {
            row[1]
            for row in connection.execute("PRAGMA table_info(character_cards)")
        }


def test_migration_adds_columns_to_existing_database(tmp_path):
    path = tmp_path / "memory.db"
    create_legacy_schema(path)
    CardRepo(path)
    assert {"tts_voice", "tts_autoplay_on_card"} <= columns(path)


def test_migration_is_idempotent_for_new_database(tmp_path):
    path = tmp_path / "memory.db"
    CardRepo(path)
    CardRepo(path)
    assert {"tts_voice", "tts_autoplay_on_card"} <= columns(path)


def test_upsert_persists_speech_fields(tmp_path):
    repository = CardRepo(tmp_path / "memory.db")
    card_id = repository.upsert_character(
        CharacterCard(
            id=None,
            name="Miku",
            description="Virtual singer",
            personality="Cheerful",
            tts_voice="ja-JP-NanamiNeural",
            tts_autoplay_on_card=1,
        )
    )
    card = repository.get_character(card_id)
    assert card is not None
    assert card.tts_voice == "ja-JP-NanamiNeural"
    assert card.tts_autoplay_on_card == 1


def test_migration_adds_tts_instructions_column(tmp_path):
    path = tmp_path / "memory.db"
    create_legacy_schema(path)
    CardRepo(path)
    assert "tts_instructions" in columns(path)


def test_upsert_persists_tts_instructions(tmp_path):
    repository = CardRepo(tmp_path / "memory.db")
    card_id = repository.upsert_character(
        CharacterCard(
            id=None,
            name="Miku",
            description="Virtual singer",
            personality="Cheerful",
            tts_instructions="speak cheerfully",
        )
    )
    card = repository.get_character(card_id)
    assert card is not None
    assert card.tts_instructions == "speak cheerfully"

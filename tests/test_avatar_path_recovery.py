# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.memory.cards import CardRepo, CharacterCard


def _repo(tmp: str) -> CardRepo:
    db_path = Path(tmp) / "memory.db"
    repo = CardRepo(db_path)
    with sqlite3.connect(db_path) as conn:
        repo.ensure_tables(conn)
    return repo


def _card(card_id: int | None = None, avatar_path: str | None = None) -> CharacterCard:
    return CharacterCard(
        id=card_id,
        name="Avatar Character",
        description="",
        personality="calm",
        avatar_path=avatar_path,
    )


def test_list_recovers_an_orphaned_avatar_file():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        repo = _repo(tmp)
        card_id = repo.upsert_character(_card())
        avatars_dir = Path(tmp) / "avatars"
        avatars_dir.mkdir()
        (avatars_dir / f"{card_id}.jpg").write_bytes(b"existing avatar")

        cards = repo.list_characters()

        assert cards[0].avatar_path == f"avatars/{card_id}.jpg"
        assert repo.get_avatar_path(card_id) == f"avatars/{card_id}.jpg"


def test_update_preserves_an_existing_avatar_path():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        repo = _repo(tmp)
        card_id = repo.upsert_character(_card(avatar_path="avatars/original.jpg"))

        repo.upsert_character(_card(card_id=card_id))

        assert repo.get_avatar_path(card_id) == "avatars/original.jpg"

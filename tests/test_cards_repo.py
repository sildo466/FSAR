# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.memory.cards import CardRepo, CharacterCard


def test_ensure_tables_creates_all_three_tables():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = Path(tmp) / "test.db"
        repo = CardRepo(db)
        with sqlite3.connect(db) as conn:
            repo.ensure_tables(conn)
            names = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        assert "character_cards" in names
        assert "user_cards" in names
        assert "emotion_audit" in names


@pytest.fixture
def repo():
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "test.db"
        r = CardRepo(db)
        with sqlite3.connect(db) as conn:
            r.ensure_tables(conn)
        yield r


def _make_card(**overrides) -> CharacterCard:
    now = "2026-07-09T00:00:00"
    base = dict(
        id=None, name="FSAR", description="test desc",
        personality="friendly", emotion_state={"affection": 50},
    )
    base.update(overrides)
    base.setdefault("created_at", now)
    base.setdefault("updated_at", now)
    return CharacterCard(**base)


def test_upsert_and_get_character(repo):
    card = _make_card()
    cid = repo.upsert_character(card)
    fetched = repo.get_character(cid)
    assert fetched is not None
    assert fetched.name == "FSAR"
    assert fetched.description == "test desc"
    assert fetched.emotion_state == {"affection": 50}


def test_list_characters_empty(repo):
    assert repo.list_characters() == []


def test_list_characters_returns_all(repo):
    repo.upsert_character(_make_card(name="A"))
    repo.upsert_character(_make_card(name="B"))
    names = [c.name for c in repo.list_characters()]
    assert names == ["A", "B"]


def test_set_default_character(repo):
    a = repo.upsert_character(_make_card(name="A"))
    b = repo.upsert_character(_make_card(name="B"))
    repo.set_default_character(b)
    assert repo.get_default_character().id == b
    assert repo.get_character(a).is_default == 0


def test_set_default_only_one_default_at_a_time(repo):
    a = repo.upsert_character(_make_card(name="A", is_default=1))
    b = repo.upsert_character(_make_card(name="B"))
    repo.set_default_character(b)
    rows = repo.list_characters()
    defaults = [c.id for c in rows if c.is_default == 1]
    assert defaults == [b]


def test_delete_character(repo):
    cid = repo.upsert_character(_make_card(name="X"))
    assert repo.delete_character(cid) is True
    assert repo.get_character(cid) is None


def test_delete_character_returns_false_when_missing(repo):
    assert repo.delete_character(999) is False
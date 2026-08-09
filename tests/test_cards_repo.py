# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.memory.cards import CardRepo, CharacterCard, UserCard


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
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
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


def test_upsert_character_update_branch_persists_changes(repo):
    cid = repo.upsert_character(
        _make_card(name="FSAR", description="old desc", tags=["a", "b"])
    )
    fetched = repo.get_character(cid)
    assert fetched is not None
    fetched.description = "new desc"
    fetched.tags = ["x", "y", "z"]
    assert fetched.id is not None
    repo.upsert_character(fetched)
    reloaded = repo.get_character(cid)
    assert reloaded is not None
    assert reloaded.description == "new desc"
    assert reloaded.tags == ["x", "y", "z"]
    assert reloaded.name == "FSAR"


def _make_user(**overrides) -> UserCard:
    now = "2026-07-09T00:00:00"
    base = dict(
        id=None, name="default-user",
        description="FSAR owner, prefers Chinese",
        preferences={"language": "zh"},
    )
    base.update(overrides)
    base.setdefault("created_at", now)
    base.setdefault("updated_at", now)
    return UserCard(**base)


def test_upsert_and_get_user_card(repo):
    card = _make_user()
    cid = repo.upsert_user_card(card)
    fetched = repo.get_user_card(cid)
    assert fetched.name == "default-user"
    assert fetched.preferences == {"language": "zh"}


def test_get_default_user_card(repo):
    repo.upsert_user_card(_make_user(name="X"))
    default = repo.upsert_user_card(_make_user(name="Y", is_default=1))
    assert repo.get_default_user_card().id == default


def test_set_default_user_card_only_one_default(repo):
    a = repo.upsert_user_card(_make_user(name="A", is_default=1))
    b = repo.upsert_user_card(_make_user(name="B"))
    repo.set_default_user_card(b)
    defaults = [u.id for u in repo.list_user_cards() if u.is_default == 1]
    assert defaults == [b]


def test_list_user_cards_empty(repo):
    assert repo.list_user_cards() == []


def test_list_user_cards_returns_all(repo):
    repo.upsert_user_card(_make_user(name="A"))
    repo.upsert_user_card(_make_user(name="B"))
    names = [c.name for c in repo.list_user_cards()]
    assert names == ["A", "B"]


def test_delete_user_card(repo):
    cid = repo.upsert_user_card(_make_user(name="X"))
    assert repo.delete_user_card(cid) is True
    assert repo.get_user_card(cid) is None


def test_delete_user_card_returns_false_when_missing(repo):
    assert repo.delete_user_card(999) is False


def test_upsert_user_card_update_branch_persists_changes(repo):
    cid = repo.upsert_user_card(
        _make_user(name="owner", description="old desc", interests=["a", "b"])
    )
    fetched = repo.get_user_card(cid)
    assert fetched is not None
    fetched.description = "new desc"
    fetched.interests = ["x", "y", "z"]
    fetched.preferences = {"language": "en"}
    assert fetched.id is not None
    repo.upsert_user_card(fetched)
    reloaded = repo.get_user_card(cid)
    assert reloaded is not None
    assert reloaded.description == "new desc"
    assert reloaded.interests == ["x", "y", "z"]
    assert reloaded.preferences == {"language": "en"}
    assert reloaded.name == "owner"

def test_upsert_character_applies_default_emotion_when_empty(repo):
    card = _make_card(emotion_state=None, emotion_schema=None, emotion_formulas=None)
    cid = repo.upsert_character(card)
    fetched = repo.get_character(cid)
    assert fetched is not None
    assert fetched.emotion_state == {"affection": 50, "trust": 50, "mood": 0, "energy": 50,
                                      "empathy": 50, "playfulness": 50, "formality": 50}
    assert len(fetched.emotion_schema) == 7
    assert "energy" in fetched.emotion_formulas


def test_set_and_get_emotion_state(repo):
    cid = repo.upsert_character(_make_card(name="X"))
    new_state = {"affection": 80, "mood": 30, "energy": 20, "trust": 60,
                 "empathy": 50, "playfulness": 50, "formality": 50}
    repo.set_emotion_state(cid, new_state)
    assert repo.get_emotion_state(cid) == new_state


def test_append_emotion_audit_writes_row(repo):
    import sqlite3
    cid = repo.upsert_character(_make_card(name="X"))
    audit_id = repo.append_emotion_audit(
        character_id=cid, session_id="s1",
        metric_key="affection", old_value=50, new_value=55,
        reason="user shared story",
    )
    assert audit_id > 0
    with sqlite3.connect(repo._db) as conn:
        rows = conn.execute(
            "SELECT character_id, metric_key, old_value, new_value, reason, session_id, delta "
            "FROM emotion_audit WHERE character_id = ?", (cid,)
        ).fetchall()
    assert len(rows) == 1
    assert rows[0][1] == "affection"
    assert rows[0][2] == 50
    assert rows[0][3] == 55
    assert rows[0][4] == "user shared story"
    assert rows[0][5] == "s1"
    assert rows[0][6] == 5


def test_set_emotion_schema_and_formulas_persists(repo):
    cid = repo.upsert_character(_make_card(name="X"))
    schema = [{"key": "calm", "min": 0, "max": 100, "initial": 50}]
    formulas = {"calm": "calm + 1"}
    repo.set_emotion_schema_and_formulas(cid, schema, formulas)
    assert repo.get_emotion_schema(cid) == schema
    assert repo.get_emotion_formulas(cid) == formulas


def test_seed_builtins_inserts_six_characters_and_one_user(tmp_path):
    import shutil
    data_dir = Path(tmp_path) / "data"
    data_dir.mkdir()
    real_data = Path(__file__).parent.parent / "data" / "cards"
    if real_data.exists():
        shutil.copytree(real_data, data_dir / "cards")
    db = Path(tmp_path) / "test.db"
    r = CardRepo(db)
    from src.memory import cards as cards_mod
    original = cards_mod.DEFAULT_EMOTION_PATH
    cards_mod.DEFAULT_EMOTION_PATH = data_dir / "emotion_default.json"
    if not (data_dir / "emotion_default.json").exists():
        shutil.copy(real_data.parent / "emotion_default.json",
                    data_dir / "emotion_default.json")
    try:
        with sqlite3.connect(db) as conn:
            r.ensure_tables(conn)
        count = r.seed_builtins_if_empty()
    finally:
        cards_mod.DEFAULT_EMOTION_PATH = original
    assert count == 6
    assert len(r.list_characters()) == 6
    assert r.get_default_user_card() is not None


def test_seed_is_idempotent(repo):
    count1 = repo.seed_builtins_if_empty()
    count2 = repo.seed_builtins_if_empty()
    assert count1 == 0 or count2 == 0

# SPDX-License-Identifier: MIT
from __future__ import annotations

import tempfile
from pathlib import Path

from src.memory.rooms import RoomStore
from src.memory.session_store import SessionStore


def _store() -> RoomStore:
    tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    db = Path(tmp.name) / "test.db"
    return RoomStore(db, SessionStore(db))


def test_create_makes_room_with_own_session() -> None:
    rooms = _store()
    room = rooms.create(name="Island", character_ids=[1, 2])
    assert room.id is not None
    assert room.session_id


def test_create_room_session_is_group_kind() -> None:
    rooms = _store()
    room = rooms.create(name="Island", character_ids=[1])
    assert rooms.session_store.get_kind(room.session_id) == "group"


def test_group_sessions_stay_out_of_chat_history_listing() -> None:
    rooms = _store()
    rooms.create(name="Island", character_ids=[1])
    solo = rooms.session_store.create()
    listed = [row.id for row in rooms.session_store.list()]
    assert solo.id in listed
    assert all(rooms.session_store.get_kind(sid) == "chat" for sid in listed)


def test_create_persists_fields_and_members() -> None:
    rooms = _store()
    room = rooms.create(
        name="Island",
        description="stranded",
        scenario_prompt="We must survive.",
        user_card_id=3,
        character_ids=[5, 6],
    )
    fetched = rooms.get(room.id)
    assert fetched is not None
    assert fetched.description == "stranded"
    assert fetched.scenario_prompt == "We must survive."
    assert fetched.user_card_id == 3
    assert rooms.members(room.id) == [5, 6]


def test_add_and_remove_members() -> None:
    rooms = _store()
    room = rooms.create(name="R", character_ids=[1])
    rooms.add_members(room.id, [2, 3])
    assert set(rooms.members(room.id)) == {1, 2, 3}
    assert rooms.remove_member(room.id, 2) is True
    assert set(rooms.members(room.id)) == {1, 3}
    assert rooms.remove_member(room.id, 99) is False


def test_add_members_is_idempotent() -> None:
    rooms = _store()
    room = rooms.create(name="R", character_ids=[1])
    rooms.add_members(room.id, [1, 2])
    assert set(rooms.members(room.id)) == {1, 2}


def test_update_changes_and_pins() -> None:
    rooms = _store()
    room = rooms.create(name="R", character_ids=[1])
    updated = rooms.update(room.id, name="R2", pinned=True)
    assert updated is not None
    assert updated.name == "R2"
    assert updated.pinned is True


def test_update_leaves_unspecified_fields_untouched() -> None:
    rooms = _store()
    room = rooms.create(name="R", description="keep me", character_ids=[1])
    rooms.update(room.id, name="R2")
    fetched = rooms.get(room.id)
    assert fetched is not None
    assert fetched.description == "keep me"


def test_update_unknown_room_returns_none() -> None:
    rooms = _store()
    assert rooms.update(4242, name="nope") is None


def test_list_pins_first_then_recent() -> None:
    rooms = _store()
    a = rooms.create(name="A", character_ids=[1])
    b = rooms.create(name="B", character_ids=[1])
    rooms.update(a.id, pinned=True)
    listed = [r.id for r in rooms.list()]
    assert listed[0] == a.id
    assert b.id in listed


def test_delete_removes_room_members_and_session_messages() -> None:
    rooms = _store()
    room = rooms.create(name="R", character_ids=[1, 2])
    rooms.session_store.append_message(room.session_id, "user", "hi")
    assert rooms.delete(room.id) is True
    assert rooms.get(room.id) is None
    assert rooms.members(room.id) == []
    assert rooms.session_store.get(room.session_id) is None
    assert rooms.session_store.get_session_messages(room.session_id) == []


def test_delete_unknown_room_returns_false() -> None:
    rooms = _store()
    assert rooms.delete(4242) is False


def test_members_of_unknown_room_is_empty() -> None:
    rooms = _store()
    assert rooms.members(4242) == []


def test_rooms_default_to_no_round_cap() -> None:
    """0 means the chain has no cap, so a room can hold an open-ended debate."""
    rooms = _store()
    room = rooms.create(name="R", character_ids=[1])
    assert room.max_rounds == 0
    assert rooms.get(room.id).max_rounds == 0


def test_create_persists_a_round_cap() -> None:
    rooms = _store()
    room = rooms.create(name="R", character_ids=[1], max_rounds=6)
    assert rooms.get(room.id).max_rounds == 6


def test_negative_round_cap_is_clamped_to_unlimited() -> None:
    rooms = _store()
    room = rooms.create(name="R", character_ids=[1], max_rounds=-3)
    assert rooms.get(room.id).max_rounds == 0


def test_update_sets_and_clears_the_round_cap() -> None:
    rooms = _store()
    room = rooms.create(name="R", character_ids=[1])
    assert rooms.update(room.id, max_rounds=8).max_rounds == 8
    assert rooms.update(room.id, max_rounds=0).max_rounds == 0


def test_update_leaves_the_round_cap_alone_when_omitted() -> None:
    rooms = _store()
    room = rooms.create(name="R", character_ids=[1], max_rounds=3)
    rooms.update(room.id, name="R2")
    assert rooms.get(room.id).max_rounds == 3


def test_max_rounds_migration_is_idempotent_on_an_old_table() -> None:
    import sqlite3
    import tempfile
    from pathlib import Path as _Path

    tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    db = _Path(tmp.name) / "old.db"
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE rooms ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, "
            "description TEXT NOT NULL DEFAULT '', scenario_prompt TEXT NOT NULL DEFAULT '', "
            "session_id TEXT NOT NULL, user_card_id INTEGER, "
            "pinned INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, "
            "updated_at TEXT NOT NULL)"
        )
        conn.commit()

    store = RoomStore(db, SessionStore(db))
    store._ensure_tables(store._connect())
    room = store.create(name="R", character_ids=[1], max_rounds=5)
    assert store.get(room.id).max_rounds == 5


def test_messages_with_speaker_delegates_to_session() -> None:
    rooms = _store()
    room = rooms.create(name="R", character_ids=[7])
    rooms.session_store.append_message(
        room.session_id, "assistant", "hello", character_card_id=7,
    )
    rows = rooms.messages_with_speaker(room.id)
    assert len(rows) == 1
    assert rows[0].character_card_id == 7


def test_messages_with_speaker_unknown_room_is_empty() -> None:
    rooms = _store()
    assert rooms.messages_with_speaker(4242) == []


def test_prune_missing_members_drops_orphans() -> None:
    rooms = _store()
    with rooms._connect() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS character_cards "
            "(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)"
        )
        conn.execute("INSERT INTO character_cards (id, name) VALUES (7, 'Mira')")
        conn.commit()
    room = rooms.create(name="R", character_ids=[7, 8])
    assert set(rooms.members(room.id)) == {7, 8}

    removed = rooms.prune_missing_members()

    assert removed == 1
    assert rooms.members(room.id) == [7]


def test_prune_missing_members_without_card_table_is_noop() -> None:
    rooms = _store()
    room = rooms.create(name="R", character_ids=[7])
    assert rooms.prune_missing_members() == 0
    assert rooms.members(room.id) == [7]

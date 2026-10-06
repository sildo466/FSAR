# SPDX-License-Identifier: MIT
"""The three columns P3b needs on rooms: a project binding, a goal, a phase."""

from __future__ import annotations

from src.memory.rooms import RoomStore
from src.memory.session_store import SessionStore


def _store(tmp_path) -> RoomStore:
    sessions = SessionStore(tmp_path / "memory.db")
    return RoomStore(tmp_path / "memory.db", sessions)


def test_a_new_room_starts_unbound_and_in_chat(tmp_path) -> None:
    store = _store(tmp_path)
    room = store.create(name="R", character_ids=[])

    assert room.workspace_id is None
    assert room.goal == ""
    assert room.phase == "chat"


def test_the_three_values_survive_a_round_trip(tmp_path) -> None:
    store = _store(tmp_path)
    room = store.create(name="R", character_ids=[])

    store.update(room.id, workspace_id=4, goal="ship the parser", phase="planning")
    reloaded = store.get(room.id)

    assert reloaded.workspace_id == 4
    assert reloaded.goal == "ship the parser"
    assert reloaded.phase == "planning"


def test_updating_one_leaves_the_others_alone(tmp_path) -> None:
    store = _store(tmp_path)
    room = store.create(name="R", character_ids=[])
    store.update(room.id, workspace_id=4, goal="g", phase="working")

    store.update(room.id, phase="review")

    reloaded = store.get(room.id)
    assert reloaded.workspace_id == 4
    assert reloaded.goal == "g"
    assert reloaded.phase == "review"


def test_update_cannot_clear_the_workspace_by_omission(tmp_path) -> None:
    """None means 'leave alone'. A caller that forgets the argument must not
    silently unbind the room's project."""
    store = _store(tmp_path)
    room = store.create(name="R", character_ids=[])
    store.update(room.id, workspace_id=4)

    store.update(room.id, goal="something else")

    assert store.get(room.id).workspace_id == 4


def test_clearing_the_workspace_needs_its_own_door(tmp_path) -> None:
    store = _store(tmp_path)
    room = store.create(name="R", character_ids=[])
    store.update(room.id, workspace_id=4)

    store.clear_workspace(room.id)

    assert store.get(room.id).workspace_id is None


def test_the_migration_is_idempotent_on_an_old_table(tmp_path) -> None:
    """Reopening a store whose rooms table predates these columns must not
    raise, and must not clobber what is already there."""
    import sqlite3

    path = tmp_path / "memory.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE rooms (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, "
        "description TEXT NOT NULL DEFAULT '', scenario_prompt TEXT NOT NULL DEFAULT '', "
        "session_id TEXT NOT NULL, user_card_id INTEGER, pinned INTEGER NOT NULL DEFAULT 0, "
        "max_rounds INTEGER NOT NULL DEFAULT 0, agent_mode INTEGER NOT NULL DEFAULT 0, "
        "lan_enabled INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT INTO rooms (name, session_id, created_at, updated_at) "
        "VALUES ('old', 's-old', 't', 't')"
    )
    conn.commit()
    conn.close()

    store = _store(tmp_path)
    old = store.list()[0]

    assert old.name == "old"
    assert old.phase == "chat"
    assert old.workspace_id is None


def test_the_room_dict_carries_the_new_fields(tmp_path) -> None:
    store = _store(tmp_path)
    room = store.create(name="R", character_ids=[])
    store.update(room.id, goal="g", phase="working")

    payload = store.get(room.id).to_dict()

    assert payload["goal"] == "g"
    assert payload["phase"] == "working"
    assert payload["workspace_id"] is None

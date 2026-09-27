# SPDX-License-Identifier: MIT
"""Room shape switches: agent mode and LAN exposure."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.memory.rooms import RoomStore
from src.memory.session_store import SessionStore


@pytest.fixture()
def store() -> RoomStore:
    tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    db = Path(tmp.name) / "test.db"
    return RoomStore(db, SessionStore(db))


def test_new_room_defaults_to_both_switches_off(store: RoomStore) -> None:
    room = store.create(name="Companion", character_ids=[7])
    assert room.agent_mode is False
    assert room.lan_enabled is False


def test_switches_persist_and_survive_reread(store: RoomStore) -> None:
    room = store.create(name="Work", character_ids=[7], agent_mode=True)
    reread = store.get(room.id)
    assert reread is not None
    assert reread.agent_mode is True
    assert reread.lan_enabled is False
    assert reread.to_dict()["agent_mode"] is True


def test_update_flips_switch_without_touching_the_other(store: RoomStore) -> None:
    room = store.create(name="Work", character_ids=[7], agent_mode=True)
    updated = store.update(room.id, lan_enabled=True)
    assert updated is not None
    assert updated.lan_enabled is True
    assert updated.agent_mode is True


def test_update_omitting_switch_leaves_it_alone(store: RoomStore) -> None:
    room = store.create(name="Work", character_ids=[7], agent_mode=True)
    updated = store.update(room.id, name="Renamed")
    assert updated is not None
    assert updated.agent_mode is True
    assert updated.name == "Renamed"


def test_migration_is_idempotent() -> None:
    tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    db = Path(tmp.name) / "test.db"
    RoomStore(db, SessionStore(db))
    second = RoomStore(db, SessionStore(db))
    assert second.create(name="X", character_ids=[7]).agent_mode is False

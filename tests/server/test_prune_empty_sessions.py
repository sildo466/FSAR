# SPDX-License-Identifier: MIT
from __future__ import annotations

from pathlib import Path

import pytest

from src.memory.session_store import SessionStore
from src.server.handlers.conversation import prune_empty_sessions


@pytest.fixture
def store(tmp_path: Path) -> SessionStore:
    return SessionStore(tmp_path / "s.db")


def _ids(store: SessionStore) -> set[str]:
    return {row.id for row in store.list(limit=500)}


def test_sweeps_a_titled_empty_session(store: SessionStore):
    """A cancelled turn persists no messages, yet the title generator has
    already named the session from the input — so the shell is not real use."""
    row = store.create()
    store.rename(row.id, "delete it")

    prune_empty_sessions(store, active_id=None)

    assert row.id not in _ids(store)


def test_sweeps_an_untitled_empty_session(store: SessionStore):
    row = store.create()

    prune_empty_sessions(store, active_id=None)

    assert row.id not in _ids(store)


def test_keeps_a_session_with_messages(store: SessionStore):
    row = store.create()
    store.rename(row.id, "hello")
    store.append_message(row.id, "user", "hi")

    prune_empty_sessions(store, active_id=None)

    assert row.id in _ids(store)


def test_keeps_the_active_conversation(store: SessionStore):
    row = store.create()
    store.rename(row.id, "delete it")

    prune_empty_sessions(store, active_id=row.id)

    assert row.id in _ids(store)


def test_keeps_pinned_sessions(store: SessionStore):
    row = store.create()
    store.rename(row.id, "delete it")
    store.set_pinned(row.id, True)

    prune_empty_sessions(store, active_id=None)

    assert row.id in _ids(store)


def test_keeps_group_rooms(store: SessionStore):
    """Rooms are not conversations and must never be swept."""
    room = store.create(kind="group")

    prune_empty_sessions(store, active_id=None)

    assert store.get(room.id) is not None

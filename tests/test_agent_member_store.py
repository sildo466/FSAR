# SPDX-License-Identifier: MIT
"""External agents as room members."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.memory.agent_members import AgentMemberStore


@pytest.fixture()
def store() -> AgentMemberStore:
    tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    return AgentMemberStore(Path(tmp.name) / "members.db")


def test_add_then_list(store: AgentMemberStore) -> None:
    store.add(1, ref="claude-laptop", display_name="Claude @ laptop")
    store.add(1, ref="codex", display_name="Codex")
    refs = [m.ref for m in store.members(1)]
    assert refs == ["claude-laptop", "codex"]


def test_new_member_is_active(store: AgentMemberStore) -> None:
    member = store.add(1, ref="claude-laptop", display_name="Claude")
    assert member.state == "active"


def test_same_ref_twice_in_a_room_is_rejected(store: AgentMemberStore) -> None:
    store.add(1, ref="claude-laptop", display_name="Claude")
    with pytest.raises(Exception):
        store.add(1, ref="claude-laptop", display_name="Other")


def test_same_ref_may_exist_in_two_rooms(store: AgentMemberStore) -> None:
    store.add(1, ref="claude-laptop", display_name="Claude")
    store.add(2, ref="claude-laptop", display_name="Claude")
    assert store.get(2, "claude-laptop") is not None


def test_set_state_mutes_and_unmutes(store: AgentMemberStore) -> None:
    store.add(1, ref="claude-laptop", display_name="Claude")
    assert store.set_state(1, "claude-laptop", "muted") is True
    assert store.get(1, "claude-laptop").state == "muted"
    assert store.set_state(1, "claude-laptop", "active") is True
    assert store.get(1, "claude-laptop").state == "active"


def test_set_state_rejects_unknown_state(store: AgentMemberStore) -> None:
    store.add(1, ref="claude-laptop", display_name="Claude")
    with pytest.raises(ValueError):
        store.set_state(1, "claude-laptop", "exploded")


def test_set_state_on_missing_member_is_false(store: AgentMemberStore) -> None:
    assert store.set_state(1, "nobody", "muted") is False


def test_remove_is_idempotent_bool(store: AgentMemberStore) -> None:
    store.add(1, ref="claude-laptop", display_name="Claude")
    assert store.remove(1, "claude-laptop") is True
    assert store.remove(1, "claude-laptop") is False
    assert store.members(1) == []


def test_members_are_room_scoped(store: AgentMemberStore) -> None:
    store.add(1, ref="a", display_name="A")
    assert store.members(2) == []

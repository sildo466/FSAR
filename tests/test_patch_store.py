# SPDX-License-Identifier: MIT
"""The patch queue: who sent what, and whether it has been settled."""

from __future__ import annotations

from src.memory.patches import PatchStore


def _store(tmp_path) -> PatchStore:
    return PatchStore(tmp_path / "memory.db")


def _add(store, *, digest="a" * 64, item_key=None, text="diff --git a/x b/x\n"):
    return store.add(1, "claude-laptop", patch_text=text, digest=digest,
                     size=len(text), item_key=item_key)


def test_a_fresh_room_has_nothing_waiting(tmp_path) -> None:
    assert _store(tmp_path).list(1) == []


def test_a_patch_waits_until_it_is_settled(tmp_path) -> None:
    patch = _add(_store(tmp_path))

    assert patch.state == "pending"
    assert patch.member_ref == "claude-laptop"
    assert patch.decided_by is None


def test_the_same_patch_does_not_queue_twice(tmp_path) -> None:
    store = _store(tmp_path)

    first = _add(store)
    second = _add(store)

    assert first.id == second.id
    assert len(store.list(1)) == 1


def test_the_list_projection_leaves_the_text_behind(tmp_path) -> None:
    store = _store(tmp_path)
    patch = _add(store, text="diff --git a/secret b/secret\n")

    assert "patch_text" not in patch.to_dict()
    assert store.text(1, patch.id) == "diff --git a/secret b/secret\n"


def test_settling_a_patch_records_who_did_it(tmp_path) -> None:
    store = _store(tmp_path)
    patch = _add(store)

    settled = store.decide(1, patch.id, "landed", reason="ok", decided_by="user")

    assert settled.state == "landed"
    assert settled.decided_by == "user"
    assert settled.decided_at


def test_a_settled_patch_cannot_be_settled_again(tmp_path) -> None:
    store = _store(tmp_path)
    patch = _add(store)
    store.decide(1, patch.id, "landed", decided_by="user")

    assert store.decide(1, patch.id, "rejected", decided_by="user") is None
    assert store.get(1, patch.id).state == "landed"


def test_a_patch_of_another_room_is_not_reachable(tmp_path) -> None:
    store = _store(tmp_path)
    patch = _add(store)

    assert store.get(2, patch.id) is None
    assert store.text(2, patch.id) is None
    assert store.decide(2, patch.id, "landed", decided_by="user") is None


def test_a_new_patch_for_the_same_item_supersedes_the_old_one(tmp_path) -> None:
    store = _store(tmp_path)
    first = _add(store, digest="1" * 64, item_key="a")
    other = _add(store, digest="2" * 64, item_key="b")

    assert store.supersede_pending(1, "a") == 1
    assert store.get(1, first.id).state == "superseded"
    assert store.get(1, other.id).state == "pending"

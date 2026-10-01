# SPDX-License-Identifier: MIT
"""The room's plan board: one writer, addressed by the model's stable key."""

from __future__ import annotations

from src.memory.room_plan import RoomPlanStore


def _item(key: str, text: str = "t", **over) -> dict:
    base = {"id": key, "text": text, "status": "todo"}
    base.update(over)
    return base


def test_a_fresh_room_has_an_empty_board(tmp_path) -> None:
    store = RoomPlanStore(tmp_path / "memory.db")
    assert store.list(1) == []


def test_replace_writes_the_whole_list(tmp_path) -> None:
    store = RoomPlanStore(tmp_path / "memory.db")

    items = store.replace(1, [
        _item("a", "parse the config"),
        _item("b", "write the tests", owner={"kind": "character", "ref": "7"}),
    ])

    assert [i.item_key for i in items] == ["a", "b"]
    assert items[1].owner_kind == "character"
    assert items[1].owner_ref == "7"
    assert items[0].owner_kind is None


def test_a_key_missing_from_the_new_list_is_dropped(tmp_path) -> None:
    store = RoomPlanStore(tmp_path / "memory.db")
    store.replace(1, [_item("a"), _item("b")])

    items = store.replace(1, [_item("b")])

    assert [i.item_key for i in items] == ["b"]


def test_replacing_keeps_the_commit_and_lease_a_already_set(tmp_path) -> None:
    """A member's plan_write must not be able to erase the promote record or
    the lease — those are A's, not the model's."""
    store = RoomPlanStore(tmp_path / "memory.db")
    store.replace(1, [_item("a")])
    store.claim(1, "a", "2099-01-01T00:00:00")
    store.set_commit_ref(1, "a", "abc123")

    items = store.replace(1, [_item("a", "reworded", status="done")])

    assert items[0].text == "reworded"
    assert items[0].status == "done"
    assert items[0].commit_ref == "abc123"
    assert items[0].lease_expires_at == "2099-01-01T00:00:00"


def test_boards_of_two_rooms_do_not_mix(tmp_path) -> None:
    store = RoomPlanStore(tmp_path / "memory.db")
    store.replace(1, [_item("a")])

    assert store.list(2) == []
    assert [i.item_key for i in store.list(1)] == ["a"]


def test_set_status_reports_evidence_without_touching_the_owner(tmp_path) -> None:
    store = RoomPlanStore(tmp_path / "memory.db")
    store.replace(1, [_item("a", owner={"kind": "character", "ref": "7"})])

    item = store.set_status(1, "a", "done", evidence="tests pass")

    assert item.status == "done"
    assert item.evidence == "tests pass"
    assert item.owner_ref == "7"


def test_set_status_on_a_missing_key_is_a_no_op(tmp_path) -> None:
    store = RoomPlanStore(tmp_path / "memory.db")
    assert store.set_status(1, "nope", "done") is None


def test_set_status_refuses_a_status_it_does_not_know(tmp_path) -> None:
    store = RoomPlanStore(tmp_path / "memory.db")
    store.replace(1, [_item("a")])

    try:
        store.set_status(1, "a", "finished")
    except ValueError:
        pass
    else:
        raise AssertionError("an unknown status must be refused")

    assert store.list(1)[0].status == "todo"


def test_an_unknown_status_from_the_model_falls_back_to_todo(tmp_path) -> None:
    """The model is not the schema. It must not be able to park an item in a
    state the scheduler cannot read."""
    store = RoomPlanStore(tmp_path / "memory.db")
    items = store.replace(1, [_item("a", status="finished")])
    assert items[0].status == "todo"


def test_claim_and_release_move_the_lease(tmp_path) -> None:
    store = RoomPlanStore(tmp_path / "memory.db")
    store.replace(1, [_item("a")])

    assert store.claim(1, "a", "2099-01-01T00:00:00") is True
    assert store.list(1)[0].status == "doing"
    assert store.list(1)[0].lease_expires_at == "2099-01-01T00:00:00"

    assert store.clear_lease(1, "a") is True
    assert store.list(1)[0].lease_expires_at is None


def test_claiming_a_missing_key_changes_nothing(tmp_path) -> None:
    store = RoomPlanStore(tmp_path / "memory.db")
    assert store.claim(1, "nope", "2099-01-01T00:00:00") is False


def test_attempts_accumulate_per_item(tmp_path) -> None:
    store = RoomPlanStore(tmp_path / "memory.db")
    store.replace(1, [_item("a")])

    store.bump_attempts(1, "a")
    store.bump_attempts(1, "a")

    assert store.list(1)[0].attempts == 2


def test_an_item_without_an_id_is_skipped(tmp_path) -> None:
    store = RoomPlanStore(tmp_path / "memory.db")
    items = store.replace(1, [_item(""), _item("a")])
    assert [i.item_key for i in items] == ["a"]


def test_the_dict_shape_is_json_ready(tmp_path) -> None:
    store = RoomPlanStore(tmp_path / "memory.db")
    store.replace(1, [_item("a")])
    payload = store.list(1)[0].to_dict()
    assert payload["item_key"] == "a"
    assert payload["status"] == "todo"
    assert payload["commit_ref"] is None

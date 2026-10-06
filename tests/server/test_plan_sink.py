# SPDX-License-Identifier: MIT
"""The seam the plan tool writes through.

One implementation today (the room) and a documented place for the chat one
later. The sink owns owner validation: a model may not invent a member.
"""

from __future__ import annotations

from src.memory.room_plan import RoomPlanStore
from src.memory.rooms import RoomStore
from src.memory.session_store import SessionStore
from src.server.plan_sink import RoomPlanSink


def _sink(tmp_path, member_ids=(7,)):
    db = tmp_path / "memory.db"
    sessions = SessionStore(db)
    rooms = RoomStore(db, sessions)
    room = rooms.create(name="R", character_ids=list(member_ids))
    plans = RoomPlanStore(db)
    return RoomPlanSink(rooms, plans, room.id), plans, room


def test_items_land_on_the_board(tmp_path) -> None:
    sink, plans, room = _sink(tmp_path)

    out = sink.replace([{"id": "a", "text": "do it", "status": "todo"}])

    assert out[0]["item_key"] == "a"
    assert [i.item_key for i in plans.list(room.id)] == ["a"]


def test_an_owner_that_is_not_a_member_is_stored_unowned(tmp_path) -> None:
    """A model must not be able to name a member that is not in the room."""
    sink, plans, room = _sink(tmp_path, member_ids=(7,))

    sink.replace([{
        "id": "a", "text": "do it", "status": "todo",
        "owner": {"kind": "character", "ref": "999"},
    }])

    assert plans.list(room.id)[0].owner_kind is None
    assert plans.list(room.id)[0].owner_ref is None


def test_a_real_member_keeps_the_ownership(tmp_path) -> None:
    sink, plans, room = _sink(tmp_path, member_ids=(7,))

    sink.replace([{
        "id": "a", "text": "do it", "status": "todo",
        "owner": {"kind": "character", "ref": "7"},
    }])

    assert plans.list(room.id)[0].owner_ref == "7"


def test_an_agent_owner_is_rejected_in_p3(tmp_path) -> None:
    """P3 dispatches to character cards only. An agent ref has nothing to
    dispatch to, so it is stored unowned rather than left looking assigned."""
    sink, plans, room = _sink(tmp_path, member_ids=(7,))

    sink.replace([{
        "id": "a", "text": "do it", "status": "todo",
        "owner": {"kind": "agent", "ref": "claude"},
    }])

    assert plans.list(room.id)[0].owner_kind is None


def test_a_non_numeric_character_ref_is_rejected(tmp_path) -> None:
    sink, plans, room = _sink(tmp_path, member_ids=(7,))

    sink.replace([{
        "id": "a", "text": "do it", "status": "todo",
        "owner": {"kind": "character", "ref": "not-an-id"},
    }])

    assert plans.list(room.id)[0].owner_kind is None


def test_a_malformed_owner_is_rejected_rather_than_raising(tmp_path) -> None:
    sink, plans, room = _sink(tmp_path)

    sink.replace([{"id": "a", "text": "t", "status": "todo", "owner": "mira"}])

    assert plans.list(room.id)[0].owner_kind is None


def test_non_dict_entries_are_dropped(tmp_path) -> None:
    sink, plans, room = _sink(tmp_path)
    sink.replace(["nonsense", {"id": "a", "text": "t", "status": "todo"}])
    assert [i.item_key for i in plans.list(room.id)] == ["a"]


def test_the_returned_payload_is_json_ready(tmp_path) -> None:
    sink, _plans, _room = _sink(tmp_path)
    out = sink.replace([{"id": "a", "text": "t", "status": "todo"}])
    assert isinstance(out, list) and isinstance(out[0], dict)


def test_the_last_written_board_is_kept_for_the_event(tmp_path) -> None:
    """The tool emits the board it just wrote; re-reading it from the store
    would race with anything else touching it."""
    sink, _plans, _room = _sink(tmp_path)
    sink.replace([{"id": "a", "text": "t", "status": "todo"}])
    assert [i["item_key"] for i in sink.last_written] == ["a"]

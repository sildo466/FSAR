# SPDX-License-Identifier: MIT
"""The scheduler: reclaim, then hand out, then decide where the room is."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from src.memory.room_plan import RoomPlanStore
from src.memory.rooms import RoomStore
from src.memory.session_store import SessionStore
from src.server.room_runner import RoomRunner


def _fixture(tmp_path, *, phase="working"):
    db = tmp_path / "memory.db"
    rooms = RoomStore(db, SessionStore(db))
    room = rooms.create(name="R", character_ids=[7])
    rooms.update(room.id, phase=phase, workspace_id=1)
    plans = RoomPlanStore(db)
    sent: list[dict] = []
    dispatched: list[tuple] = []

    async def dispatch(r, item, workspace):
        dispatched.append((r.id, item.item_key, workspace))

    async def emit(payload):
        sent.append(payload)

    clock = SimpleNamespace(now=datetime(2026, 10, 1, tzinfo=timezone.utc))
    runner = RoomRunner(
        rooms, plans, dispatch, emit,
        now=lambda: clock.now, max_in_flight=2, lease_seconds=900,
    )
    return SimpleNamespace(
        rooms=rooms, room=room, plans=plans, sent=sent,
        dispatched=dispatched, runner=runner, clock=clock,
    )


def _owned(key="a", text="t"):
    return {"id": key, "text": text, "status": "todo",
            "owner": {"kind": "character", "ref": "7"}}


def test_planning_moves_to_working_once_every_item_is_owned(tmp_path) -> None:
    f = _fixture(tmp_path, phase="planning")
    f.plans.replace(f.room.id, [_owned()])

    reason = asyncio.run(f.runner.tick(f.rooms.get(f.room.id)))

    assert reason == "all_owned"
    assert f.rooms.get(f.room.id).phase == "working"
    assert [m["type"] for m in f.sent] == ["room.phase.changed"]
    assert f.sent[0]["reason"] == "all_owned"


def test_an_owned_todo_is_handed_out_and_leased(tmp_path) -> None:
    f = _fixture(tmp_path)
    f.plans.replace(f.room.id, [_owned()])

    reason = asyncio.run(f.runner.tick(f.rooms.get(f.room.id)))

    assert reason == "dispatched"
    assert len(f.dispatched) == 1
    item = f.plans.list(f.room.id)[0]
    assert item.status == "doing"
    assert item.lease_expires_at is not None


def test_the_cap_holds_the_line_at_max_in_flight(tmp_path) -> None:
    f = _fixture(tmp_path)
    f.plans.replace(f.room.id, [_owned("a"), _owned("b"), _owned("c")])

    asyncio.run(f.runner.tick(f.rooms.get(f.room.id)))

    assert len(f.dispatched) == 2
    statuses = {i.item_key: i.status for i in f.plans.list(f.room.id)}
    assert statuses == {"a": "doing", "b": "doing", "c": "todo"}


def test_an_expired_lease_is_reclaimed_and_counted(tmp_path) -> None:
    """A turn that vanished must not hold the room hostage."""
    f = _fixture(tmp_path)
    f.plans.replace(f.room.id, [_owned()])
    f.plans.claim(f.room.id, "a", "2020-01-01T00:00:00")

    reclaimed = asyncio.run(f.runner.reclaim(f.rooms.get(f.room.id)))

    assert reclaimed == 1
    item = f.plans.list(f.room.id)[0]
    assert item.status == "todo"
    assert item.lease_expires_at is None
    assert item.attempts == 1


def test_a_live_lease_is_left_alone(tmp_path) -> None:
    f = _fixture(tmp_path)
    f.plans.replace(f.room.id, [_owned()])
    future = f.clock.now + timedelta(hours=1)
    f.plans.claim(f.room.id, "a", future.isoformat())

    assert asyncio.run(f.runner.reclaim(f.rooms.get(f.room.id))) == 0
    assert f.plans.list(f.room.id)[0].status == "doing"


def test_an_item_that_keeps_dying_is_marked_blocked(tmp_path) -> None:
    f = _fixture(tmp_path)
    f.plans.replace(f.room.id, [_owned()])
    for _ in range(3):
        f.plans.claim(f.room.id, "a", "2020-01-01T00:00:00")
        asyncio.run(f.runner.reclaim(f.rooms.get(f.room.id)))

    item = f.plans.list(f.room.id)[0]
    assert item.status == "blocked"
    assert item.attempts == 3


def test_a_blocked_item_is_not_handed_out_again(tmp_path) -> None:
    f = _fixture(tmp_path)
    f.plans.replace(f.room.id, [_owned()])
    f.plans.set_status(f.room.id, "a", "blocked", evidence="gave up")

    asyncio.run(f.runner.tick(f.rooms.get(f.room.id)))

    assert f.dispatched == []


def test_a_room_with_nothing_left_stops_and_says_why(tmp_path) -> None:
    f = _fixture(tmp_path)
    f.plans.replace(f.room.id, [_owned()])
    f.plans.set_status(f.room.id, "a", "done", evidence="ok")

    reason = asyncio.run(f.runner.tick(f.rooms.get(f.room.id)))

    assert reason == "all_done"
    assert f.rooms.get(f.room.id).phase == "review"
    assert f.sent[-1]["type"] == "room.phase.changed"
    assert f.sent[-1]["reason"] == "all_done"


def test_a_room_with_a_running_turn_does_not_advance(tmp_path) -> None:
    """A `doing` item with a live lease is work in progress, whoever started
    it — including a process that has since restarted."""
    f = _fixture(tmp_path)
    f.plans.replace(f.room.id, [_owned()])
    f.plans.claim(f.room.id, "a", "2099-01-01T00:00:00")

    assert asyncio.run(f.runner.tick(f.rooms.get(f.room.id))) == "busy"
    assert f.rooms.get(f.room.id).phase == "working"


def test_a_room_that_is_not_working_is_left_alone(tmp_path) -> None:
    f = _fixture(tmp_path, phase="chat")
    f.plans.replace(f.room.id, [_owned()])

    assert asyncio.run(f.runner.tick(f.rooms.get(f.room.id))) == "idle"
    assert f.dispatched == []


def test_a_room_in_review_is_not_ticked(tmp_path) -> None:
    f = _fixture(tmp_path, phase="review")
    f.plans.replace(f.room.id, [_owned()])

    assert asyncio.run(f.runner.tick(f.rooms.get(f.room.id))) == "idle"
    assert f.dispatched == []


def test_the_item_with_no_owner_stops_the_room_with_its_own_reason(tmp_path) -> None:
    f = _fixture(tmp_path)
    f.plans.replace(f.room.id, [{"id": "a", "text": "t", "status": "todo"}])

    reason = asyncio.run(f.runner.tick(f.rooms.get(f.room.id)))

    assert reason == "no_owner"
    assert f.rooms.get(f.room.id).phase == "review"


def test_reclaiming_pushes_the_board_so_the_gui_catches_up(tmp_path) -> None:
    f = _fixture(tmp_path)
    f.plans.replace(f.room.id, [_owned()])
    f.plans.claim(f.room.id, "a", "2020-01-01T00:00:00")

    asyncio.run(f.runner.reclaim(f.rooms.get(f.room.id)))

    assert [m["type"] for m in f.sent] == ["room.plan.updated"]


def test_handing_out_pushes_the_board_too(tmp_path) -> None:
    f = _fixture(tmp_path)
    f.plans.replace(f.room.id, [_owned()])

    asyncio.run(f.runner.tick(f.rooms.get(f.room.id)))

    assert "room.plan.updated" in [m["type"] for m in f.sent]


def test_a_tick_that_changes_nothing_pushes_nothing(tmp_path) -> None:
    """A planning room with an empty board is genuinely unchanged — it has
    nothing to hand out and nowhere to go yet."""
    f = _fixture(tmp_path, phase="planning")

    assert asyncio.run(f.runner.tick(f.rooms.get(f.room.id))) == "idle"
    assert f.sent == []


def test_an_empty_working_board_ends_in_review(tmp_path) -> None:
    f = _fixture(tmp_path)

    assert asyncio.run(f.runner.tick(f.rooms.get(f.room.id))) == "all_done"
    assert f.rooms.get(f.room.id).phase == "review"


def test_the_dispatch_callback_is_given_the_item_and_the_room(tmp_path) -> None:
    f = _fixture(tmp_path)
    f.plans.replace(f.room.id, [_owned("x")])

    asyncio.run(f.runner.tick(f.rooms.get(f.room.id)))

    assert f.dispatched == [(f.room.id, "x", None)]

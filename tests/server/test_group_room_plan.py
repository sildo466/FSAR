# SPDX-License-Identifier: MIT
"""The room.* messages the GUI drives the plan board with."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from src.server.handlers import group as group_handler


class FakeWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send_json(self, message: dict) -> None:
        self.messages.append(message)


def _wire(*, agent_mode=True, phase="chat", workspace_id=None, items=None):
    state: dict = {"goal": "", "phase": phase, "workspace_id": workspace_id}
    room = SimpleNamespace(id=1, session_id="s1", agent_mode=agent_mode,
                           max_rounds=0, user_card_id=None, **state)

    def _update(room_id, **kw):
        for key in ("goal", "phase", "workspace_id"):
            if kw.get(key) is not None:
                setattr(room, key, kw[key])
        return room

    def _clear_workspace(room_id):
        room.workspace_id = None
        return room

    rooms = SimpleNamespace(
        get=lambda room_id: room if room_id == 1 else None,
        members=lambda room_id: [7],
        update=_update,
        clear_workspace=_clear_workspace,
    )
    written = {"items": items or []}
    plans = SimpleNamespace(
        list=lambda room_id: [
            SimpleNamespace(to_dict=lambda i=i: dict(i)) for i in written["items"]
        ],
    )

    async def run_chain(ws, *, room, user_input, mentioned, user_card):
        return "settled"

    engine = SimpleNamespace(
        run_chain=run_chain,
        chat=SimpleNamespace(card_repo=SimpleNamespace(
            get_character=lambda c: None,
            get_user_card=lambda cid: None,
            get_default_user_card=lambda: None,
        )),
    )
    group_handler.set_engine(engine, rooms)
    group_handler.set_room_plan_engine(rooms, plans)
    group_handler._tasks.clear()
    return room, written


def _drain(ws) -> list[dict]:
    out = list(ws.messages)
    ws.messages.clear()
    return out


def test_a_goal_moves_the_room_into_planning() -> None:
    room, _ = _wire()
    ws = FakeWebSocket()

    asyncio.run(group_handler.dispatch(
        ws, {"type": "room.goal.set", "room_id": 1, "goal": "ship the parser"},
    ))

    assert room.goal == "ship the parser"
    assert room.phase == "planning"
    changed = [m for m in ws.messages if m["type"] == "room.phase.changed"]
    assert changed and changed[0]["phase"] == "planning"
    assert changed[0]["reason"] == "goal_set"


def test_setting_a_goal_sends_the_board_back() -> None:
    _room, _ = _wire()
    ws = FakeWebSocket()

    asyncio.run(group_handler.dispatch(
        ws, {"type": "room.goal.set", "room_id": 1, "goal": "g"},
    ))

    assert "room.plan.updated" in [m["type"] for m in ws.messages]


def test_listing_the_board_sends_it_back() -> None:
    _room, _written = _wire(items=[{"item_key": "a", "text": "t"}])
    ws = FakeWebSocket()

    asyncio.run(group_handler.dispatch(ws, {"type": "room.plan.list", "room_id": 1}))

    updated = [m for m in ws.messages if m["type"] == "room.plan.updated"]
    assert updated and updated[0]["items"][0]["item_key"] == "a"
    assert updated[0]["room_id"] == 1


def test_confirming_done_moves_the_room_to_done() -> None:
    room, _ = _wire(phase="review")
    ws = FakeWebSocket()

    asyncio.run(group_handler.dispatch(
        ws, {"type": "room.phase.confirm_done", "room_id": 1},
    ))

    assert room.phase == "done"
    changed = [m for m in ws.messages if m["type"] == "room.phase.changed"]
    assert changed and changed[0]["reason"] == "user_confirmed"


def test_unbinding_clears_the_workspace() -> None:
    room, _ = _wire(workspace_id=3)
    ws = FakeWebSocket()

    asyncio.run(group_handler.dispatch(ws, {"type": "room.plan.unbind", "room_id": 1}))

    assert room.workspace_id is None


def test_the_goal_is_handed_to_one_round_of_characters() -> None:
    """Without this the board would stay empty forever: nothing else turns a
    goal into plan items."""
    room, _ = _wire()
    seen: list[str] = []

    async def run_chain(ws, *, room, user_input, mentioned, user_card):
        seen.append(user_input)
        return "settled"

    group_handler._engine.run_chain = run_chain
    ws = FakeWebSocket()

    async def scenario():
        await group_handler.dispatch(
            ws, {"type": "room.goal.set", "room_id": 1, "goal": "ship the parser"},
        )
        task = group_handler._tasks.get(1)
        if task is not None:
            await task

    asyncio.run(scenario())

    assert seen == ["ship the parser"]


def test_an_empty_goal_starts_no_round() -> None:
    _wire()
    seen: list[str] = []

    async def run_chain(ws, *, room, user_input, mentioned, user_card):
        seen.append(user_input)
        return "settled"

    group_handler._engine.run_chain = run_chain
    ws = FakeWebSocket()
    asyncio.run(group_handler.dispatch(
        ws, {"type": "room.goal.set", "room_id": 1, "goal": "   "},
    ))

    assert seen == []


def test_a_room_without_agent_mode_refuses_room_messages() -> None:
    _wire(agent_mode=False)
    ws = FakeWebSocket()

    asyncio.run(group_handler.dispatch(ws, {"type": "room.plan.list", "room_id": 1}))

    err = [m for m in ws.messages if m["type"] == "group.error"]
    assert err and err[0]["code"] == "not_agent_room"


def test_an_unknown_room_gets_a_not_found() -> None:
    _wire()
    ws = FakeWebSocket()

    asyncio.run(group_handler.dispatch(ws, {"type": "room.plan.list", "room_id": 99}))

    err = [m for m in ws.messages if m["type"] == "group.error"]
    assert err and err[0]["code"] == "not_found"


def test_a_broken_action_reports_a_handler_error_rather_than_raising() -> None:
    _wire()

    def _boom(room_id, **kw):
        raise RuntimeError("boom")

    group_handler._rooms.update = _boom
    ws = FakeWebSocket()

    asyncio.run(group_handler.dispatch(
        ws, {"type": "room.goal.set", "room_id": 1, "goal": "g"},
    ))

    err = [m for m in ws.messages if m["type"] == "group.error"]
    assert err and err[0]["code"] == "group_handler"


def test_dispatcher_claims_room_messages_and_leaves_others_alone() -> None:
    _wire()
    ws = FakeWebSocket()

    assert asyncio.run(group_handler.dispatch(ws, {"type": "room.plan.list", "room_id": 1})) is True
    assert asyncio.run(group_handler.dispatch(ws, {"type": "chat.send"})) is False

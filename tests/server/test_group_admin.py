# SPDX-License-Identifier: MIT
"""Mute, kick and stop-all — the user's emergency controls over a live room."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from src.server.handlers import group as group_handler


class FakeWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send_json(self, message: dict) -> None:
        self.messages.append(message)


def _wire():
    calls: dict[str, object] = {}
    member = SimpleNamespace(ref="claude-laptop", display_name="Claude", state="active")
    agents = SimpleNamespace(
        members=lambda room_id: [member],
        get=lambda room_id, ref: member if ref == member.ref else None,
        set_state=lambda room_id, ref, state: (
            calls.update(state_set=state, state_ref=ref) or True
        ),
        remove=lambda room_id, ref: (calls.update(removed=ref) or True),
    )
    revoked: list[int] = []
    tokens = SimpleNamespace(
        list_for=lambda room_id, ref: [
            {"id": 11, "label": "a"}, {"id": 12, "label": "b"},
        ],
        revoke=lambda token_id: (revoked.append(token_id) or True),
    )
    cancelled: list[int] = []
    room = SimpleNamespace(
        id=1, session_id="s1", user_card_id=None, max_rounds=0,
        to_dict=lambda: {"id": 1, "name": "R", "session_id": "s1"},
    )
    engine = SimpleNamespace(
        chat=SimpleNamespace(session_store=SimpleNamespace()),
        cancel=lambda room_id: cancelled.append(room_id),
    )
    rooms = SimpleNamespace(
        get=lambda room_id: room,
        members=lambda room_id: [7],
        list=lambda: [room],
    )
    group_handler.set_engine(engine, rooms, agents, tokens)
    group_handler._tasks.clear()
    return calls, revoked, cancelled


def test_mute_sets_member_state() -> None:
    calls, _, _ = _wire()
    ws = FakeWebSocket()
    asyncio.run(group_handler.dispatch(
        ws, {"type": "group.agent.mute", "room_id": 1,
             "member_ref": "claude-laptop", "muted": True},
    ))
    assert calls["state_set"] == "muted"
    assert calls["state_ref"] == "claude-laptop"
    assert ws.messages[-1]["type"] == "group.updated"
    assert ws.messages[-1]["room"]["agent_members"] == [
        {"ref": "claude-laptop", "display_name": "Claude", "state": "active"},
    ]


def test_unmute_sets_active() -> None:
    calls, _, _ = _wire()
    ws = FakeWebSocket()
    asyncio.run(group_handler.dispatch(
        ws, {"type": "group.agent.mute", "room_id": 1,
             "member_ref": "claude-laptop", "muted": False},
    ))
    assert calls["state_set"] == "active"


def test_mute_on_unknown_member_emits_group_error() -> None:
    calls, _, _ = _wire()
    ws = FakeWebSocket()
    asyncio.run(group_handler.dispatch(
        ws, {"type": "group.agent.mute", "room_id": 1,
             "member_ref": "ghost", "muted": True},
    ))
    assert ws.messages[-1]["type"] == "group.error"
    assert ws.messages[-1]["code"] == "no_member"
    assert "state_set" not in calls


def test_kick_removes_member_and_revokes_every_token() -> None:
    calls, revoked, _ = _wire()
    ws = FakeWebSocket()
    asyncio.run(group_handler.dispatch(
        ws, {"type": "group.agent.remove", "room_id": 1,
             "member_ref": "claude-laptop"},
    ))
    assert calls["removed"] == "claude-laptop"
    assert revoked == [11, 12]
    assert ws.messages[-1]["type"] == "group.updated"


def test_kick_on_unknown_member_emits_group_error() -> None:
    calls, revoked, _ = _wire()
    ws = FakeWebSocket()
    asyncio.run(group_handler.dispatch(
        ws, {"type": "group.agent.remove", "room_id": 1, "member_ref": "ghost"},
    ))
    assert ws.messages[-1]["type"] == "group.error"
    assert ws.messages[-1]["code"] == "no_member"
    assert "removed" not in calls
    assert revoked == []


def test_stop_all_cancels_every_room_with_a_live_chain() -> None:
    _, _, cancelled = _wire()

    async def never() -> None:
        await asyncio.sleep(3600)

    async def scenario() -> None:
        group_handler._start_chain(1, never())
        await asyncio.sleep(0)
        ws = FakeWebSocket()
        await group_handler.dispatch(ws, {"type": "group.stop_all"})
        await asyncio.sleep(0)
        assert ws.messages[-1]["type"] == "group.stop_all.ack"

    asyncio.run(scenario())
    assert cancelled == [1]


def test_stop_all_with_nothing_running_is_harmless() -> None:
    _, _, cancelled = _wire()
    ws = FakeWebSocket()
    asyncio.run(group_handler.dispatch(ws, {"type": "group.stop_all"}))
    assert cancelled == []
    assert ws.messages[-1]["type"] == "group.stop_all.ack"

# SPDX-License-Identifier: MIT
"""The mode is chosen when the room is made and not after.

It decides which route the room's characters run on, so changing it mid-flight
would change what a room is while its members are in it. The LAN switch is the
opposite case: a network fact the owner has to be able to change without
rebuilding the room.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from src.server.handlers import group as group_handler


class FakeWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send_json(self, message: dict) -> None:
        self.messages.append(message)


def _wire() -> SimpleNamespace:
    room = SimpleNamespace(
        id=1, session_id="s1", user_card_id=None, max_rounds=0,
        agent_mode=False, lan_enabled=False,
        to_dict=lambda: {"id": 1, "name": "R", "session_id": "s1"},
    )

    def _update(room_id, **fields):
        """What RoomStore.update does: None means leave this field alone."""
        for key, value in fields.items():
            if value is not None:
                setattr(room, key, value)
        return room

    rooms = SimpleNamespace(
        get=lambda room_id: room,
        members=lambda room_id: [],
        list=lambda: [room],
        update=_update,
    )
    agents = SimpleNamespace(members=lambda room_id: [])
    engine = SimpleNamespace(
        chat=SimpleNamespace(session_store=SimpleNamespace()),
        cancel=lambda room_id: None,
    )
    group_handler.set_engine(engine, rooms, agents, None)
    group_handler._tasks.clear()
    return SimpleNamespace(room=room, rooms=rooms)


def test_turning_the_mode_on_after_the_fact_is_refused() -> None:
    wired = _wire()
    ws = FakeWebSocket()

    asyncio.run(group_handler.dispatch(
        ws, {"type": "group.update", "room_id": 1, "agent_mode": True},
    ))

    assert ws.messages[-1]["type"] == "group.error"
    assert ws.messages[-1]["code"] == "mode_not_editable"
    assert wired.room.agent_mode is False


def test_the_mode_is_refused_even_when_other_fields_ride_along() -> None:
    """A caller that bundles the mode with legitimate edits must not get the
    edits applied and the mode silently dropped."""
    wired = _wire()
    ws = FakeWebSocket()

    asyncio.run(group_handler.dispatch(
        ws, {"type": "group.update", "room_id": 1,
             "name": "renamed", "agent_mode": True},
    ))

    assert ws.messages[-1]["code"] == "mode_not_editable"
    assert wired.room.agent_mode is False


def test_the_lan_switch_is_editable_in_the_room() -> None:
    wired = _wire()
    ws = FakeWebSocket()

    asyncio.run(group_handler.dispatch(
        ws, {"type": "group.update", "room_id": 1, "lan_enabled": True},
    ))

    assert ws.messages[-1]["type"] == "group.updated"
    assert wired.room.lan_enabled is True


def test_a_mode_free_update_still_works() -> None:
    """The refusal is about the mode, not about group.update."""
    wired = _wire()
    ws = FakeWebSocket()

    asyncio.run(group_handler.dispatch(
        ws, {"type": "group.update", "room_id": 1, "name": "renamed"},
    ))

    assert ws.messages[-1]["type"] == "group.updated"

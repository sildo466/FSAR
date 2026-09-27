# SPDX-License-Identifier: MIT
"""Room shape is chosen at creation time and reaches the store."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from src.server.handlers import group as group_handler


class FakeWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send_json(self, message: dict) -> None:
        self.messages.append(message)


def _wire() -> dict:
    captured: dict = {}

    def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            id=1, name=kwargs.get("name", ""), members=[7],
            to_dict=lambda: {"id": 1, "name": kwargs.get("name", "")},
        )

    rooms = SimpleNamespace(create=create, members=lambda room_id: [7])
    group_handler.set_engine(SimpleNamespace(chat=SimpleNamespace()), rooms)
    return captured


def test_create_defaults_both_switches_off() -> None:
    captured = _wire()
    ws = FakeWebSocket()
    asyncio.run(group_handler.dispatch(ws, {
        "type": "group.create", "name": "Companion", "character_ids": [7],
    }))
    assert captured["agent_mode"] is False
    assert captured["lan_enabled"] is False
    assert ws.messages[-1]["type"] == "group.created"


def test_create_passes_both_switches_through() -> None:
    captured = _wire()
    ws = FakeWebSocket()
    asyncio.run(group_handler.dispatch(ws, {
        "type": "group.create", "name": "Work", "character_ids": [7],
        "agent_mode": True, "lan_enabled": True,
    }))
    assert captured["agent_mode"] is True
    assert captured["lan_enabled"] is True


def test_update_can_flip_a_switch() -> None:
    captured: dict = {}

    def update(room_id, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            id=room_id, to_dict=lambda: {"id": room_id}, members=[7],
        )

    rooms = SimpleNamespace(
        update=update, get=lambda room_id: SimpleNamespace(id=room_id),
        members=lambda room_id: [7],
    )
    group_handler.set_engine(SimpleNamespace(chat=SimpleNamespace()), rooms)
    ws = FakeWebSocket()
    asyncio.run(group_handler.dispatch(ws, {
        "type": "group.update", "room_id": 1, "agent_mode": False,
    }))
    assert captured["agent_mode"] is False
    assert captured["lan_enabled"] is None

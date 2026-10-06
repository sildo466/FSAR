# SPDX-License-Identifier: MIT
"""The room.* messages the GUI drives publishing with."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from src.memory.publishes import PublishStore
from src.server.handlers import group as group_handler


class FakeWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send_json(self, message: dict) -> None:
        self.messages.append(message)


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("FSAR_HOME", str(tmp_path / "home"))


def _wire(tmp_path, *, project: bool = True):
    root = tmp_path / "project"
    root.mkdir()
    (root / "app.py").write_text("x = 1\n", encoding="utf-8")

    room = SimpleNamespace(
        id=1, session_id="s1", agent_mode=True, max_rounds=0,
        user_card_id=None, goal="", phase="chat", workspace_id=3,
    )
    rooms = SimpleNamespace(
        get=lambda room_id: room if room_id == 1 else None,
        members=lambda room_id: [7],
        update=lambda *a, **kw: room,
        clear_workspace=lambda room_id: room,
    )
    plans = SimpleNamespace(list=lambda room_id: [])
    publishes = PublishStore(tmp_path / "memory.db")

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
    group_handler.set_room_publish(
        publishes, lambda live_room: str(root) if project else None,
    )
    group_handler._tasks.clear()
    return room, publishes


def _types(ws) -> list[str]:
    return [m["type"] for m in ws.messages]


def test_a_request_with_an_allowlist_writes_a_package(tmp_path) -> None:
    _room, publishes = _wire(tmp_path)
    ws = FakeWebSocket()

    asyncio.run(group_handler.dispatch(ws, {
        "type": "room.publish.request", "room_id": 1, "allowlist": ["*.py"],
    }))

    assert "room.publish.updated" in _types(ws)
    ready = [m for m in ws.messages if m["type"] == "room.publish.ready"]
    assert ready and ready[0]["path_count"] == 1
    assert len(publishes.list(1)) == 1


def test_an_empty_allowlist_is_refused_by_name(tmp_path) -> None:
    _room, publishes = _wire(tmp_path)
    ws = FakeWebSocket()

    asyncio.run(group_handler.dispatch(ws, {
        "type": "room.publish.request", "room_id": 1, "allowlist": [],
    }))

    err = [m for m in ws.messages if m["type"] == "group.error"]
    assert err and err[0]["code"] == "no_allowlist"
    assert publishes.list(1) == []


def test_a_room_without_a_project_says_so(tmp_path) -> None:
    _room, publishes = _wire(tmp_path, project=False)
    ws = FakeWebSocket()

    asyncio.run(group_handler.dispatch(ws, {
        "type": "room.publish.request", "room_id": 1, "allowlist": ["*.py"],
    }))

    err = [m for m in ws.messages if m["type"] == "group.error"]
    assert err and err[0]["code"] == "no_project"
    assert publishes.list(1) == []


def test_listing_publishes_sends_the_ledger_back(tmp_path) -> None:
    _room, publishes = _wire(tmp_path)
    publishes.record(1, "owner", path_count=2, byte_count=20, digest="ab" * 32)
    ws = FakeWebSocket()

    asyncio.run(group_handler.dispatch(
        ws, {"type": "room.publish.list", "room_id": 1},
    ))

    updated = [m for m in ws.messages if m["type"] == "room.publish.updated"]
    assert updated and updated[0]["publishes"][0]["path_count"] == 2

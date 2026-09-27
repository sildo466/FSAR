# SPDX-License-Identifier: MIT
"""Agent members render alongside character cards, everywhere a speaker shows."""

from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace

from src.memory.session_store import MessageRow
from src.server.group_engine import format_group_history
from src.server.handlers import group as group_handler


class FakeWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send_json(self, message: dict) -> None:
        self.messages.append(message)


def _row(row_id: int, role: str, content: str, *, card_id=None,
         kind=None, ref=None) -> SimpleNamespace:
    return SimpleNamespace(
        id=row_id, session_id="s1", role=role, content=content,
        character_card_id=card_id, speaker_kind=kind, speaker_ref=ref,
        summary="", tags="", timestamp=datetime(2026, 1, 1),
    )


def _wire(rows, *, cards, agents) -> None:
    """Minimal stand-ins for the stores the handler reaches for."""
    room = SimpleNamespace(
        id=1, session_id="s1", user_card_id=None,
        scenario_prompt="", name="R", description="",
        agent_mode=True, lan_enabled=False, pinned=False, max_rounds=0,
        to_dict=lambda: {"id": 1, "name": "R", "session_id": "s1"},
    )
    rooms = SimpleNamespace(
        get=lambda room_id: room,
        members=lambda room_id: [7],
        messages_with_speaker=lambda room_id: rows,
    )
    chat = SimpleNamespace(
        session_store=SimpleNamespace(get_session_messages=lambda sid: rows),
        card_repo=SimpleNamespace(
            get_character=lambda cid: cards.get(cid),
            get_user_card=lambda cid: None,
            get_default_user_card=lambda: SimpleNamespace(name="You"),
        ),
    )
    group_handler.set_engine(SimpleNamespace(chat=chat), rooms, agents)


def test_history_renders_legacy_card_row_unchanged() -> None:
    cards = {7: SimpleNamespace(id=7, name="Mira")}
    agents = SimpleNamespace(members=lambda room_id: [])
    _wire([_row(1, "assistant", "hi", card_id=7)], cards=cards, agents=agents)
    ws = FakeWebSocket()
    asyncio.run(group_handler.dispatch(ws, {"type": "group.history", "room_id": 1}))
    msg = ws.messages[-1]["messages"][0]
    assert msg["role"] == "assistant"
    assert msg["row_id"] == 1
    assert msg["character_id"] == 7
    assert msg["character_name"] == "Mira"
    assert msg["speaker_kind"] is None
    assert msg["user_name"] is None
    assert msg["timestamp"].startswith("2026-01-01")


def test_history_renders_user_row_unchanged() -> None:
    agents = SimpleNamespace(members=lambda room_id: [])
    _wire([_row(1, "user", "hello")], cards={}, agents=agents)
    ws = FakeWebSocket()
    asyncio.run(group_handler.dispatch(ws, {"type": "group.history", "room_id": 1}))
    msg = ws.messages[-1]["messages"][0]
    assert msg["user_name"] == "You"
    assert msg["character_name"] is None
    assert msg["speaker_kind"] is None


def test_history_renders_agent_row_by_ref() -> None:
    agents = SimpleNamespace(
        members=lambda room_id: [
            SimpleNamespace(ref="claude-laptop", display_name="Claude", state="active"),
        ]
    )
    _wire(
        [_row(2, "assistant", "on it", kind="agent", ref="claude-laptop")],
        cards={}, agents=agents,
    )
    ws = FakeWebSocket()
    asyncio.run(group_handler.dispatch(ws, {"type": "group.history", "room_id": 1}))
    msg = ws.messages[-1]["messages"][0]
    assert msg["speaker_kind"] == "agent"
    assert msg["character_name"] == "Claude"
    assert msg["character_id"] is None
    assert msg["user_name"] is None


def test_history_names_an_unknown_agent_ref_without_crashing() -> None:
    agents = SimpleNamespace(members=lambda room_id: [])
    _wire(
        [_row(3, "assistant", "gone", kind="agent", ref="ghost")],
        cards={}, agents=agents,
    )
    ws = FakeWebSocket()
    asyncio.run(group_handler.dispatch(ws, {"type": "group.history", "room_id": 1}))
    assert ws.messages[-1]["messages"][0]["character_name"] == "Unknown"


def test_room_payload_carries_agent_members() -> None:
    room = SimpleNamespace(id=1, to_dict=lambda: {"id": 1})
    rooms = SimpleNamespace(members=lambda room_id: [7])
    agents = SimpleNamespace(
        members=lambda room_id: [
            SimpleNamespace(ref="claude-laptop", display_name="Claude", state="muted"),
        ]
    )
    payload = group_handler._room_payload(room, rooms, agents)
    assert payload["members"] == [7]
    assert payload["agent_members"] == [
        {"ref": "claude-laptop", "display_name": "Claude", "state": "muted"},
    ]


def test_room_payload_without_agents_is_empty_list() -> None:
    room = SimpleNamespace(id=1, to_dict=lambda: {"id": 1})
    rooms = SimpleNamespace(members=lambda room_id: [7])
    payload = group_handler._room_payload(room, rooms, SimpleNamespace(members=lambda r: []))
    assert payload["agent_members"] == []


def test_chain_history_prefixes_an_agent_row_with_its_display_name() -> None:
    rows = [
        MessageRow(id=1, session_id="s1", role="assistant", content="on it",
                   speaker_kind="agent", speaker_ref="claude-laptop"),
    ]
    out = format_group_history(
        rows, names_by_id={}, user_name="You",
        agent_names={"claude-laptop": "Claude"},
    )
    assert out == [{"role": "assistant", "content": "[Claude]: on it"}]


def test_chain_history_leaves_legacy_rows_alone() -> None:
    rows = [
        MessageRow(id=1, session_id="s1", role="assistant", content="hi",
                   character_card_id=7),
    ]
    assert format_group_history(rows, names_by_id={7: "Mira"}, user_name="You") == [
        {"role": "assistant", "content": "[Mira]: hi"},
    ]

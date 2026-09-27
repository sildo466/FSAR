# SPDX-License-Identifier: MIT
"""Adding agent members and handing out their credentials."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from src.server.handlers import group as group_handler


class FakeWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send_json(self, message: dict) -> None:
        self.messages.append(message)


def _wire(*, existing: list[str] | None = None):
    refs = list(existing or [])
    issued: list[dict] = []

    def add(room_id, *, ref, display_name):
        if ref in refs:
            raise Exception("UNIQUE constraint failed")
        refs.append(ref)
        return SimpleNamespace(ref=ref, display_name=display_name, state="active")

    agents = SimpleNamespace(
        add=add,
        remove=lambda room_id, ref: refs.remove(ref) is None if ref in refs else False,
        get=lambda room_id, ref: (
            SimpleNamespace(ref=ref, display_name=ref, state="active")
            if ref in refs else None
        ),
        members=lambda room_id: [
            SimpleNamespace(ref=r, display_name=r.upper(), state="active")
            for r in refs
        ],
    )
    tokens = SimpleNamespace(
        issue=lambda room_id, ref, **kw: (
            issued.append({"room_id": room_id, "ref": ref})
            or SimpleNamespace(token_id=1, token="secret-once",
                               room_id=room_id, member_ref=ref)
        ),
        list_for=lambda room_id, ref: [
            {"id": 1, "label": "", "created_at": "t", "last_used_at": None,
             "revoked_at": None},
        ],
        revoke=lambda token_id: True,
    )
    room = SimpleNamespace(
        id=1, to_dict=lambda: {"id": 1, "name": "R"}, members=[7],
    )
    rooms = SimpleNamespace(
        get=lambda room_id: room, members=lambda room_id: [7],
    )
    group_handler.set_engine(
        SimpleNamespace(chat=SimpleNamespace(session_store=SimpleNamespace())),
        rooms, agents, tokens,
    )
    return refs, issued


def test_add_member_emits_updated_room() -> None:
    refs, _ = _wire()
    ws = FakeWebSocket()
    asyncio.run(group_handler.dispatch(ws, {
        "type": "group.agent.add", "room_id": 1,
        "ref": "claude-laptop", "display_name": "Claude",
    }))
    assert refs == ["claude-laptop"]
    assert ws.messages[-1]["type"] == "group.updated"
    assert ws.messages[-1]["room"]["agent_members"] == [
        {"ref": "claude-laptop", "display_name": "CLAUDE-LAPTOP", "state": "active"},
    ]


def test_add_falls_back_to_the_ref_as_display_name() -> None:
    refs, _ = _wire()
    ws = FakeWebSocket()
    asyncio.run(group_handler.dispatch(ws, {
        "type": "group.agent.add", "room_id": 1, "ref": "codex", "display_name": "  ",
    }))
    assert refs == ["codex"]
    assert ws.messages[-1]["type"] == "group.updated"


def test_add_rejects_duplicate_ref() -> None:
    _wire(existing=["claude-laptop"])
    ws = FakeWebSocket()
    asyncio.run(group_handler.dispatch(ws, {
        "type": "group.agent.add", "room_id": 1,
        "ref": "claude-laptop", "display_name": "Again",
    }))
    assert ws.messages[-1]["type"] == "group.error"
    assert ws.messages[-1]["code"] == "duplicate_ref"


def test_add_rejects_empty_ref() -> None:
    refs, _ = _wire()
    ws = FakeWebSocket()
    asyncio.run(group_handler.dispatch(ws, {
        "type": "group.agent.add", "room_id": 1,
        "ref": "   ", "display_name": "Nameless",
    }))
    assert refs == []
    assert ws.messages[-1]["type"] == "group.error"
    assert ws.messages[-1]["code"] == "bad_ref"


def test_token_issue_returns_plaintext_exactly_once() -> None:
    _, issued = _wire(existing=["claude-laptop"])
    ws = FakeWebSocket()
    asyncio.run(group_handler.dispatch(ws, {
        "type": "group.agent.token.issue", "room_id": 1,
        "member_ref": "claude-laptop", "label": "laptop",
    }))
    payload = ws.messages[-1]
    assert payload["type"] == "group.agent.token.issued"
    assert payload["token"] == "secret-once"
    assert payload["token_id"] == 1
    assert payload["member_ref"] == "claude-laptop"
    assert issued == [{"room_id": 1, "ref": "claude-laptop"}]


def test_token_list_never_carries_the_secret() -> None:
    _wire(existing=["claude-laptop"])
    ws = FakeWebSocket()
    asyncio.run(group_handler.dispatch(ws, {
        "type": "group.agent.list", "room_id": 1,
    }))
    payload = ws.messages[-1]
    assert payload["type"] == "group.agent.list.ok"
    agent = payload["agents"][0]
    assert agent["ref"] == "claude-laptop"
    assert agent["state"] == "active"
    assert len(agent["tokens"]) == 1
    assert all("secret" not in str(v) for v in agent["tokens"][0].values())


def test_token_issue_for_unknown_member_is_rejected() -> None:
    _, issued = _wire()
    ws = FakeWebSocket()
    asyncio.run(group_handler.dispatch(ws, {
        "type": "group.agent.token.issue", "room_id": 1, "member_ref": "ghost",
    }))
    assert issued == []
    assert ws.messages[-1]["type"] == "group.error"
    assert ws.messages[-1]["code"] == "no_member"


def test_token_revoke_acks_with_a_fresh_list() -> None:
    _wire(existing=["claude-laptop"])
    ws = FakeWebSocket()
    asyncio.run(group_handler.dispatch(ws, {
        "type": "group.agent.token.revoke", "room_id": 1,
        "member_ref": "claude-laptop", "token_id": 1,
    }))
    assert ws.messages[-1]["type"] == "group.agent.list.ok"
    assert ws.messages[-1]["agents"][0]["ref"] == "claude-laptop"

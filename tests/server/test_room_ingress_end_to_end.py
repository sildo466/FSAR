# SPDX-License-Identifier: MIT
"""One member message, all the way to the room transcript and back.

Unlike the other ingress tests this one uses the real stores (no fakes), so a
break in the token -> member -> transcript chain shows up here. Only the
character chain is stubbed: it would otherwise need an LLM.
"""

from __future__ import annotations

from collections import defaultdict, deque
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.memory.agent_members import AgentMemberStore
from src.memory.member_tokens import MemberTokenStore
from src.memory.rooms import RoomStore
from src.memory.session_store import SessionStore
from src.server import room_ingress
from src.server.handlers import group as group_handler


@pytest.fixture()
def wired(tmp_path, monkeypatch):
    db = tmp_path / "fsar.db"
    sessions = SessionStore(db)
    rooms = RoomStore(db, sessions)
    agents = AgentMemberStore(db)
    tokens = MemberTokenStore(db)

    room = rooms.create(name="Work", character_ids=[], agent_mode=True)
    agents.add(room.id, ref="claude-laptop", display_name="Claude")
    issued = tokens.issue(room.id, "claude-laptop")

    chains: list[dict] = []

    async def fake_run_chain(ws, *, room, user_input, mentioned, user_card,
                             max_rounds_override=None):
        chains.append({
            "room_id": room.id, "user_input": user_input,
            "max_rounds_override": max_rounds_override,
        })
        return "settled"

    chat = SimpleNamespace(
        session_store=sessions,
        card_repo=SimpleNamespace(
            get_user_card=lambda cid: None,
            get_default_user_card=lambda: SimpleNamespace(name="You"),
        ),
        _render_attachments=lambda files: ("", ""),
        note_arrival=lambda conv: None,
    )
    engine = SimpleNamespace(chat=chat, run_chain=fake_run_chain)

    monkeypatch.setattr(group_handler, "_engine", engine)
    monkeypatch.setattr(group_handler, "_rooms", rooms)
    monkeypatch.setattr(group_handler, "_agent_members", agents)
    monkeypatch.setattr(group_handler, "_member_tokens", tokens)
    monkeypatch.setattr(group_handler, "_tasks", {})
    monkeypatch.setattr(room_ingress, "_tokens", tokens)
    monkeypatch.setattr(room_ingress, "_rooms", rooms)
    monkeypatch.setattr(room_ingress, "_recent", defaultdict(deque))

    app = FastAPI()
    app.include_router(room_ingress.router)
    return SimpleNamespace(
        client=TestClient(app),
        token=issued.token,
        room_id=room.id,
        db=db,
        rooms=rooms,
        room=room,
        chains=chains,
    )


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_member_message_reaches_the_room_transcript(wired) -> None:
    response = wired.client.post(
        "/api/room/member/message", json={"content": "on it"},
        headers=_auth(wired.token),
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True
    row_id = response.json()["row_id"]

    rows = wired.rooms.messages_with_speaker(wired.room_id)
    row = next(r for r in rows if r.id == row_id)
    assert row.content == "on it"
    assert row.speaker_kind == "agent"
    assert row.speaker_ref == "claude-laptop"
    assert row.character_card_id is None


def test_member_message_resumes_the_character_chain(wired) -> None:
    wired.client.post(
        "/api/room/member/message", json={"content": "on it"},
        headers=_auth(wired.token),
    )
    assert len(wired.chains) == 1
    assert wired.chains[0]["user_input"] == "on it"
    # A room with agent members must not run uncapped.
    assert wired.chains[0]["max_rounds_override"] == 4


def test_member_reads_the_room_back_through_its_cursor(wired) -> None:
    wired.client.post(
        "/api/room/member/message", json={"content": "on it"},
        headers=_auth(wired.token),
    )
    payload = wired.client.get(
        "/api/room/member/state?since=0", headers=_auth(wired.token),
    ).json()
    assert payload["room_name"] == "Work"
    assert payload["member_ref"] == "claude-laptop"
    assert [m["content"] for m in payload["messages"]] == ["on it"]
    assert payload["messages"][0]["speaker_kind"] == "agent"


def test_a_token_naming_a_foreign_room_lands_nowhere(wired) -> None:
    # A real token, but minted for a room that does not exist here. Identity is
    # the (room, member) pair, so this must not reach the transcript.
    tokens = MemberTokenStore(wired.db)
    stranger = tokens.issue(999, "claude-laptop")
    response = wired.client.post(
        "/api/room/member/message", json={"content": "hello"},
        headers=_auth(stranger.token),
    )
    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert wired.rooms.messages_with_speaker(wired.room_id) == []

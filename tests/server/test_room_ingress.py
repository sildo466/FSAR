# SPDX-License-Identifier: MIT
"""Loopback ingress: a member token is the only thing that names a room."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.memory.agent_members import AgentMemberStore
from src.memory.member_tokens import MemberTokenStore
from src.server import room_ingress
from src.server.handlers import group as group_handler


def _row(row_id: int, role: str, content: str, *, kind=None, ref=None) -> SimpleNamespace:
    return SimpleNamespace(
        id=row_id, role=role, content=content,
        character_card_id=None, speaker_kind=kind, speaker_ref=ref,
    )


@pytest.fixture()
def wired(tmp_path, monkeypatch):
    db = tmp_path / "m.db"
    agents = AgentMemberStore(db)
    tokens = MemberTokenStore(db)
    agents.add(1, ref="claude-laptop", display_name="Claude")
    issued = tokens.issue(1, "claude-laptop")
    rooms = SimpleNamespace(
        get=lambda room_id: SimpleNamespace(
            id=1, session_id="s1", name="Room One", max_rounds=0,
        ),
        members=lambda room_id: [7],
    )
    posted: list[dict] = []

    async def fake_post(*, room_id, member_ref, content, ws=None):
        posted.append(
            {"room_id": room_id, "member_ref": member_ref, "content": content}
        )
        return {"ok": True, "code": "ok", "row_id": 99}

    monkeypatch.setattr(group_handler, "post_member_message", fake_post)
    monkeypatch.setattr(
        group_handler, "_engine",
        SimpleNamespace(chat=SimpleNamespace(session_store=SimpleNamespace(
            get_session_messages=lambda sid: [
                _row(1, "user", "hi"),
                _row(2, "assistant", "on it", kind="agent", ref="claude-laptop"),
                _row(3, "assistant", "hello"),
            ],
        ))),
    )
    room_ingress._recent.clear()
    room_ingress.configure(tokens, rooms)
    app = FastAPI()
    app.include_router(room_ingress.router)
    return SimpleNamespace(
        client=TestClient(app),
        token=issued.token,
        posted=posted,
        tokens=tokens,
    )


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_message_without_token_is_401(wired) -> None:
    response = wired.client.post("/api/room/member/message", json={"content": "hi"})
    assert response.status_code == 401
    assert wired.posted == []


def test_message_with_bad_token_is_401(wired) -> None:
    response = wired.client.post(
        "/api/room/member/message", json={"content": "hi"},
        headers=_auth("nope"),
    )
    assert response.status_code == 401
    assert wired.posted == []


def test_message_with_member_token_is_accepted(wired) -> None:
    response = wired.client.post(
        "/api/room/member/message", json={"content": "hi room"},
        headers=_auth(wired.token),
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True, "code": "ok", "row_id": 99}
    assert wired.posted == [
        {"room_id": 1, "member_ref": "claude-laptop", "content": "hi room"},
    ]


def test_body_cannot_override_identity(wired) -> None:
    wired.client.post(
        "/api/room/member/message",
        json={"content": "hi", "room_id": 999, "member_ref": "someone-else"},
        headers=_auth(wired.token),
    )
    assert wired.posted[0]["room_id"] == 1
    assert wired.posted[0]["member_ref"] == "claude-laptop"


def test_revoked_token_is_rejected(wired) -> None:
    rows = wired.tokens.list_for(1, "claude-laptop")
    wired.tokens.revoke(int(rows[0]["id"]))
    response = wired.client.post(
        "/api/room/member/message", json={"content": "hi"},
        headers=_auth(wired.token),
    )
    assert response.status_code == 401


def test_oversized_body_is_413(wired) -> None:
    response = wired.client.post(
        "/api/room/member/message",
        json={"content": "x" * (16 * 1024 + 1)},
        headers=_auth(wired.token),
    )
    assert response.status_code == 413
    assert wired.posted == []


def test_rate_limit_trips_after_the_configured_burst(wired, monkeypatch) -> None:
    monkeypatch.setattr(room_ingress, "_MEMBER_MAX_PER_MINUTE", 2)
    room_ingress._recent.clear()
    codes = [
        wired.client.post(
            "/api/room/member/message", json={"content": "x"},
            headers=_auth(wired.token),
        ).status_code
        for _ in range(3)
    ]
    assert codes == [200, 200, 429]


def test_state_needs_a_token(wired) -> None:
    assert wired.client.get("/api/room/member/state").status_code == 401


def test_state_names_the_member_and_honours_the_cursor(wired) -> None:
    response = wired.client.get(
        "/api/room/member/state?since=1", headers=_auth(wired.token),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["room_id"] == 1
    assert payload["room_name"] == "Room One"
    assert payload["member_ref"] == "claude-laptop"
    assert [m["row_id"] for m in payload["messages"]] == [2, 3]
    assert payload["messages"][0]["speaker_kind"] == "agent"

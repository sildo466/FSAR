# SPDX-License-Identifier: MIT
"""GET /room/index — the only room a credential may know about."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.memory.agent_members import AgentMemberStore
from src.memory.auth_audit import AuthAuditStore
from src.memory.lan_blocklist import LanBlocklist
from src.memory.member_tokens import MemberTokenStore
from src.memory.rooms import RoomStore
from src.memory.session_store import SessionStore
from src.security.rate_budget import RateBudget
from src.server.room_app import RoomDeps, create_room_app


def _wire(tmp_path, *, client_host: str = "192.168.1.20"):
    db = tmp_path / "lan.db"
    sessions = SessionStore(db)
    rooms = RoomStore(db, sessions)
    members = AgentMemberStore(db)
    tokens = MemberTokenStore(db)
    room = rooms.create(name="Work", character_ids=[], agent_mode=True,
                        lan_enabled=True)
    members.add(room.id, ref="claude-laptop", display_name="Claude")
    issued = tokens.issue(room.id, "claude-laptop")
    deps = RoomDeps(
        tokens=tokens, blocklist=LanBlocklist(db), audit=AuthAuditStore(db),
        rooms=rooms, members=members, budget=RateBudget(),
    )
    return SimpleNamespace(
        client=TestClient(create_room_app(deps), client=(client_host, 40000)),
        token=issued.token, token_id=issued.token_id, room=room, rooms=rooms,
        members=members, tokens=tokens, deps=deps,
    )


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_index_lists_the_tokens_own_room(tmp_path) -> None:
    wired = _wire(tmp_path)
    response = wired.client.get("/room/index", headers=_auth(wired.token))
    assert response.status_code == 200
    body = response.json()
    assert [entry["room_id"] for entry in body["rooms"]] == [wired.room.id]
    entry = body["rooms"][0]
    assert entry["name"] == "Work"
    assert entry["member_ref"] == "claude-laptop"
    assert entry["display_name"] == "Claude"
    assert entry["state"] == "active"
    assert entry["max_rounds"] == 0


def test_index_never_hints_at_other_rooms(tmp_path) -> None:
    wired = _wire(tmp_path)
    wired.rooms.create(name="Secret Project", character_ids=[],
                       agent_mode=True, lan_enabled=True)
    body = wired.client.get("/room/index", headers=_auth(wired.token)).json()
    assert len(body["rooms"]) == 1
    assert "Secret Project" not in json.dumps(body)


def test_a_muted_member_still_sees_its_room_and_its_state(tmp_path) -> None:
    wired = _wire(tmp_path)
    wired.members.set_state(wired.room.id, "claude-laptop", "muted")
    entry = wired.client.get(
        "/room/index", headers=_auth(wired.token)
    ).json()["rooms"][0]
    assert entry["state"] == "muted"


def test_a_revoked_token_cannot_list_anything(tmp_path) -> None:
    wired = _wire(tmp_path)
    wired.tokens.revoke(wired.token_id)
    response = wired.client.get("/room/index", headers=_auth(wired.token))
    assert response.status_code == 401


def test_a_removed_member_cannot_list_anything(tmp_path) -> None:
    """Its credential is still valid; its membership is not."""
    wired = _wire(tmp_path)
    wired.members.remove(wired.room.id, "claude-laptop")
    assert wired.client.get(
        "/room/index", headers=_auth(wired.token)
    ).status_code == 404


def test_a_room_with_lan_off_is_invisible(tmp_path) -> None:
    wired = _wire(tmp_path)
    wired.rooms.update(wired.room.id, lan_enabled=False)
    assert wired.client.get(
        "/room/index", headers=_auth(wired.token)
    ).status_code == 404


def test_index_needs_a_token(tmp_path) -> None:
    wired = _wire(tmp_path)
    assert wired.client.get("/room/index").status_code == 401


def test_an_address_change_is_refused(tmp_path) -> None:
    wired = _wire(tmp_path)
    assert wired.client.get(
        "/room/index", headers=_auth(wired.token)
    ).status_code == 200
    elsewhere = TestClient(create_room_app(wired.deps), client=("10.0.0.9", 40000))
    assert elsewhere.get(
        "/room/index", headers=_auth(wired.token)
    ).status_code == 401


def test_get_is_the_only_method_index_answers(tmp_path) -> None:
    wired = _wire(tmp_path)
    response = wired.client.post("/room/index", headers=_auth(wired.token))
    assert response.status_code == 405
    assert response.json()["code"] == "method_not_allowed"


def test_the_read_is_audited_without_the_credential(tmp_path) -> None:
    wired = _wire(tmp_path)
    wired.client.get("/room/index", headers=_auth(wired.token))
    blob = json.dumps(wired.deps.audit.list(limit=50), ensure_ascii=False)
    assert "lan_read" in blob
    assert wired.token not in blob

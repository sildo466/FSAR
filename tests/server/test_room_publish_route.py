# SPDX-License-Identifier: MIT
"""GET /room/{room_id}/publish — the snapshot a member works from."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.memory.agent_members import AgentMemberStore
from src.memory.auth_audit import AuthAuditStore
from src.memory.lan_blocklist import LanBlocklist
from src.memory.member_tokens import MemberTokenStore
from src.memory.publishes import PublishStore
from src.memory.rooms import RoomStore
from src.memory.session_store import SessionStore
from src.security.rate_budget import RateBudget
from src.server.publish_export import package_for
from src.server.room_app import RoomDeps, create_room_app


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("FSAR_HOME", str(tmp_path / "home"))


def _wire(tmp_path, *, lan_enabled: bool = True, publish: bool = True):
    db = tmp_path / "lan.db"
    sessions = SessionStore(db)
    rooms = RoomStore(db, sessions)
    members = AgentMemberStore(db)
    tokens = MemberTokenStore(db)
    publishes = PublishStore(db)
    room = rooms.create(name="Work", character_ids=[], agent_mode=True,
                        lan_enabled=lan_enabled)
    members.add(room.id, ref="claude-laptop", display_name="Claude")
    issued = tokens.issue(room.id, "claude-laptop")
    if publish:
        path = package_for(room.id, "cd" * 32)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"snapshot-bytes")
        publishes.record(room.id, "claude-laptop", path_count=2,
                         byte_count=path.stat().st_size, digest="cd" * 32)
    deps = RoomDeps(
        tokens=tokens, blocklist=LanBlocklist(db), audit=AuthAuditStore(db),
        rooms=rooms, members=members, budget=RateBudget(),
        publishes=publishes,
    )
    return SimpleNamespace(
        client=TestClient(create_room_app(deps), client=("192.168.1.20", 40000)),
        token=issued.token, room=room, rooms=rooms, members=members,
    )


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _get(wired):
    return wired.client.get(
        f"/room/{wired.room.id}/publish", headers=_auth(wired.token)
    )


def test_the_snapshot_comes_back(tmp_path) -> None:
    wired = _wire(tmp_path)
    response = _get(wired)
    assert response.status_code == 200
    assert response.content == b"snapshot-bytes"


def test_a_room_that_has_published_nothing_is_404(tmp_path) -> None:
    wired = _wire(tmp_path, publish=False)
    response = _get(wired)
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_the_snapshot_needs_a_token(tmp_path) -> None:
    wired = _wire(tmp_path)
    assert wired.client.get(f"/room/{wired.room.id}/publish").status_code == 401


def test_a_room_with_lan_off_is_404(tmp_path) -> None:
    wired = _wire(tmp_path, lan_enabled=False)
    assert _get(wired).status_code == 404


def test_a_removed_member_is_404(tmp_path) -> None:
    wired = _wire(tmp_path)
    wired.members.remove(wired.room.id, "claude-laptop")
    assert _get(wired).status_code == 404


def test_another_room_is_404(tmp_path) -> None:
    wired = _wire(tmp_path)
    other = wired.rooms.create(name="Other", character_ids=[],
                               agent_mode=True, lan_enabled=True)
    response = wired.client.get(
        f"/room/{other.id}/publish", headers=_auth(wired.token)
    )
    assert response.status_code == 404

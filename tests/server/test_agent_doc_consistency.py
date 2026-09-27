# SPDX-License-Identifier: MIT
"""agent.md is pinned to the surface it describes, in both directions.

A member acts on what that document says, so a line describing a route that
does not exist — or a route nobody documented — is a behaviour bug, not a typo.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.memory.agent_members import AgentMemberStore
from src.memory.auth_audit import AuthAuditStore
from src.memory.idempotency import IdempotencyStore
from src.memory.lan_blocklist import LanBlocklist
from src.memory.member_tokens import MemberTokenStore
from src.memory.rooms import RoomStore
from src.memory.session_store import SessionStore
from src.security.rate_budget import RateBudget
from src.server import room_app
from src.server.agent_doc import AGENT_MD
from src.server.room_app import RoomDeps, create_room_app

PATH_RE = re.compile(r"/room/[A-Za-z0-9_{}/.]*")


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
        idempotency=IdempotencyStore(db),
    )
    app = create_room_app(deps)
    return SimpleNamespace(
        app=app, client=TestClient(app, client=(client_host, 40000)),
        token=issued.token, token_id=issued.token_id, tokens=tokens,
        room=room, rooms=rooms, members=members, deps=deps,
    )


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _flat(text: str) -> str:
    return " ".join(text.split())


def _registered(app) -> set[tuple[str, str]]:
    return {
        (route.path, method)
        for route in app.routes
        for method in getattr(route, "methods", set()) or set()
        if method in {"GET", "POST"}
    }


def test_the_app_exposes_exactly_four_routes(tmp_path) -> None:
    """The whole containment argument: these four, and nothing else."""
    assert _registered(_wire(tmp_path).app) == {
        ("/room/index", "GET"),
        ("/room/{room_id}/state", "GET"),
        ("/room/{room_id}/messages", "POST"),
        ("/room/agent.md", "GET"),
    }


def test_every_route_is_documented_with_its_method(tmp_path) -> None:
    for path, method in _registered(_wire(tmp_path).app):
        assert path in AGENT_MD, path
        assert method in AGENT_MD, (path, method)


def test_every_path_the_doc_mentions_is_a_real_route(tmp_path) -> None:
    registered = {path for path, _ in _registered(_wire(tmp_path).app)}
    documented = {
        match.group(0).replace("/room/1/", "/room/{room_id}/")
        for match in PATH_RE.finditer(AGENT_MD)
    }
    assert documented <= registered, documented - registered


def test_the_doc_never_promises_the_plan_endpoint(tmp_path) -> None:
    """It arrives in P3; documenting it now would be a lie."""
    assert "/plan/" not in AGENT_MD


def test_the_doc_never_promises_what_p2_does_not_have(tmp_path) -> None:
    flat = AGENT_MD.lower()
    for absent in ("history_from", "phase", "plan item", "lease", "staging"):
        assert absent not in flat, absent


def test_the_documented_limits_match_the_budgets() -> None:
    """The prose and the numbers have to move together."""
    speak_limit, speak_window, speak_burst = room_app.SPEAK_BUDGET
    room_limit, room_window, room_burst = room_app.ROOM_SPEAK_BUDGET
    read_limit, read_window, read_burst = room_app.READ_BUDGET
    flat = _flat(AGENT_MD)
    assert speak_window == 60 and room_window == 60 and read_window == 60, (
        "the document says 'per minute'; change it and this test together"
    )
    assert f"{speak_limit} messages per minute per member" in flat
    assert f"{room_limit} per minute for the whole room" in flat
    # The bursts too: the document used to quote only the sustained rate, so a
    # caller budgeting for 20 a minute hit the wall on its fifth quick send.
    assert f"a burst of {speak_burst}" in flat
    assert f"a burst of {room_burst}" in flat
    assert f"{read_limit} per minute with a burst of {read_burst}" in flat
    assert f"{room_app.MAX_CONTENT_BYTES // 1024} KiB" in flat


def test_the_doc_never_carries_a_real_credential(tmp_path) -> None:
    wired = _wire(tmp_path)
    assert wired.token not in AGENT_MD
    assert "$FSAR_ROOM_TOKEN" in AGENT_MD


def test_the_doc_is_served_as_markdown(tmp_path) -> None:
    wired = _wire(tmp_path)
    response = wired.client.get("/room/agent.md", headers=_auth(wired.token))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.text == AGENT_MD


def test_the_doc_needs_a_token(tmp_path) -> None:
    wired = _wire(tmp_path)
    assert wired.client.get("/room/agent.md").status_code == 401


def test_a_revoked_token_cannot_fetch_the_doc(tmp_path) -> None:
    wired = _wire(tmp_path)
    wired.tokens.revoke(wired.token_id)
    assert wired.client.get(
        "/room/agent.md", headers=_auth(wired.token)
    ).status_code == 401

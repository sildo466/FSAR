# SPDX-License-Identifier: MIT
"""Acceptance sweep for the network-facing surface.

The other suites check that each piece does what it was designed to do. This
one tries to get in: it assumes an attacker on the LAN who has the address and
nothing else. Each test names the scenario it comes from in the design doc.
"""

from __future__ import annotations

import json
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
from src.server.agent_doc import agent_md
from src.server.room_app import RoomDeps, create_room_app

STRANGER_IP = "203.0.113.7"

PROBE_PATHS = [
    "/", "/docs", "/redoc", "/openapi.json", "/health", "/metrics", "/ws",
    "/api/ws-token", "/api/config", "/api/models", "/api/rooms", "/api/tools",
    "/api/memory", "/api/settings", "/room", "/room/", "/room/1",
    "/room/1/state", "/room/1/messages", "/room/1/plan/2/status",
    "/room/plan", "/room/index", "/room/agent.md", "/../../etc/passwd",
]


def _wire(tmp_path, *, client_host: str = STRANGER_IP):
    db = tmp_path / "lan.db"
    sessions = SessionStore(db)
    rooms = RoomStore(db, sessions)
    members = AgentMemberStore(db)
    tokens = MemberTokenStore(db)
    room = rooms.create(name="Secret Project", character_ids=[],
                        agent_mode=True, lan_enabled=True)
    members.add(room.id, ref="claude-laptop", display_name="Claude")
    issued = tokens.issue(room.id, "claude-laptop")
    deps = RoomDeps(
        tokens=tokens, blocklist=LanBlocklist(db), audit=AuthAuditStore(db),
        rooms=rooms, members=members, budget=RateBudget(),
        idempotency=IdempotencyStore(db),
    )
    return SimpleNamespace(
        deps=deps, room=room, token=issued.token, tokens=tokens,
        sessions=sessions, rooms=rooms, members=members,
        client=TestClient(create_room_app(deps), client=(client_host, 40000)),
    )


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- A01: a stranger with only the address ------------------------------------


def test_a01_a_stranger_learns_nothing_from_any_path(tmp_path) -> None:
    wired = _wire(tmp_path)
    for path in PROBE_PATHS:
        response = wired.client.get(path)
        assert response.status_code in (401, 403, 404, 405), (path, response.status_code)
        body = response.text
        assert "Secret Project" not in body, path
        assert "claude-laptop" not in body, path
        assert "Traceback" not in body, path
        assert "room_name" not in body, path


def test_a01_nothing_answers_a_lan_request_until_tls_is_terminated(tmp_path) -> None:
    """The listener is TLS-only; there is no plaintext path to fall back to.

    Asserted here as a property of the app: it has no route that answers an
    unauthenticated request with data, so a TLS failure cannot expose one."""
    wired = _wire(tmp_path)
    answered = [
        path for path in PROBE_PATHS
        if wired.client.get(path).status_code in (200, 201, 202)
    ]
    assert answered == []


def test_a01_a_post_only_path_does_not_leak_either(tmp_path) -> None:
    wired = _wire(tmp_path)
    response = wired.client.post(
        f"/room/{wired.room.id}/messages", json={"content": "hi"},
    )
    assert response.status_code == 401
    assert "Secret Project" not in response.text


# --- A02: credentials ------------------------------------------------------


def test_a02_a_token_from_the_wrong_address_is_refused(tmp_path) -> None:
    wired = _wire(tmp_path, client_host="192.168.1.20")
    assert wired.client.get(
        "/room/index", headers=_auth(wired.token)
    ).status_code == 200
    stranger = TestClient(create_room_app(wired.deps), client=("198.51.100.9", 40000))
    response = stranger.get("/room/index", headers=_auth(wired.token))
    assert response.status_code == 401
    assert "claude-laptop" not in response.text


def test_a02_the_gui_token_does_not_open_the_room_api(tmp_path) -> None:
    """The two credential kinds must never interchange."""
    from src.security.ws_auth import WSAuthenticator

    wired = _wire(tmp_path)
    gui_token = WSAuthenticator().ensure_token()
    assert gui_token
    assert wired.client.get(
        "/room/index", headers=_auth(gui_token)
    ).status_code == 401


def test_a02_a_revoked_credential_stops_working_immediately(tmp_path) -> None:
    wired = _wire(tmp_path, client_host="192.168.1.20")
    assert wired.client.get(
        "/room/index", headers=_auth(wired.token)
    ).status_code == 200
    wired.tokens.revoke(wired.tokens.list_for(wired.room.id, "claude-laptop")[0]["id"])
    assert wired.client.get(
        "/room/index", headers=_auth(wired.token)
    ).status_code == 401


# --- A05: data publication scope ------------------------------------------


def test_a05_index_never_hints_at_other_rooms(tmp_path) -> None:
    wired = _wire(tmp_path, client_host="192.168.1.20")
    wired.rooms.create(name="Another Secret", character_ids=[],
                       agent_mode=True, lan_enabled=True)
    body = wired.client.get("/room/index", headers=_auth(wired.token)).json()
    assert len(body["rooms"]) == 1
    assert "Another Secret" not in json.dumps(body)


def test_a05_index_names_the_members_of_the_room(tmp_path) -> None:
    """A member cannot address anyone it cannot see, so index lists them."""
    wired = _wire(tmp_path, client_host="192.168.1.20")
    wired.members.add(wired.room.id, ref="ori-box", display_name="Ori")
    body = wired.client.get("/room/index", headers=_auth(wired.token)).json()
    listed = {m["ref"]: m for m in body["rooms"][0]["members"]}
    assert listed["claude-laptop"]["display_name"] == "Claude"
    assert listed["ori-box"]["display_name"] == "Ori"
    assert all(m["kind"] == "agent" for m in listed.values())


def test_a05_since_zero_returns_only_the_credentials_own_room(tmp_path) -> None:
    wired = _wire(tmp_path, client_host="192.168.1.20")
    other = wired.rooms.create(name="Elsewhere", character_ids=[],
                               agent_mode=True, lan_enabled=True)
    wired.sessions.append_message(other.session_id, "user", "not yours")
    wired.sessions.append_message(wired.room.session_id, "user", "yours")
    body = wired.client.get(
        f"/room/{wired.room.id}/state?since=0", headers=_auth(wired.token)
    ).json()
    assert [m["content"] for m in body["messages"]] == ["yours"]


def test_a05_a_room_with_lan_off_publishes_nothing(tmp_path) -> None:
    wired = _wire(tmp_path, client_host="192.168.1.20")
    wired.rooms.update(wired.room.id, lan_enabled=False)
    assert wired.client.get(
        f"/room/{wired.room.id}/state", headers=_auth(wired.token)
    ).status_code == 404


# --- A06: the management plane is unreachable ------------------------------


def test_a06_a_forged_forwarded_header_cannot_move_the_anchor(tmp_path) -> None:
    wired = _wire(tmp_path)
    forged = {
        "X-Forwarded-For": "192.168.1.99",
        "X-Real-IP": "192.168.1.99",
        "Forwarded": "for=192.168.1.99",
    }
    assert wired.client.get(
        "/room/index", headers={**_auth(wired.token), **forged},
    ).status_code == 200
    assert wired.tokens.resolve_record(wired.token).bound_ip == STRANGER_IP


def test_a06_a_forged_host_header_changes_nothing(tmp_path) -> None:
    wired = _wire(tmp_path, client_host="192.168.1.20")
    response = wired.client.get(
        "/room/index", headers={**_auth(wired.token), "Host": "evil.example"},
    )
    assert response.status_code == 200
    assert "evil.example" not in response.text


def test_a06_the_lan_app_registers_no_management_route(tmp_path) -> None:
    app = create_room_app(_wire(tmp_path).deps)
    paths = {route.path for route in app.routes}
    for forbidden in (
        "/ws", "/api/ws-token", "/api/config", "/api/models", "/api/tools",
        "/api/settings", "/api/memory", "/api/rooms",
    ):
        assert forbidden not in paths


# --- A15: abuse control ----------------------------------------------------


def test_a15_an_unauthenticated_flood_is_bounded(tmp_path) -> None:
    wired = _wire(tmp_path)
    codes = [wired.client.get("/room/index").status_code for _ in range(60)]
    assert codes[0] == 401
    assert 429 in codes, "the flood was never refused"


def test_a15_a_flood_does_not_stop_a_valid_credential(tmp_path) -> None:
    """The per-source bucket must not lock out the member on that address."""
    wired = _wire(tmp_path, client_host="192.168.1.20")
    for _ in range(60):
        wired.client.get("/room/index", headers=_auth("not-a-token"))
    assert wired.client.get(
        "/room/index", headers=_auth(wired.token)
    ).status_code == 200


def test_a15_a_flood_leaves_the_gui_app_answering(tmp_path) -> None:
    """The LAN surface has its own budget object; the GUI app never consults
    it, so a LAN flood cannot become a GUI outage."""
    import src.server.ws_server as ws_server

    wired = _wire(tmp_path)
    gui = TestClient(ws_server.app)
    for _ in range(60):
        wired.client.get("/room/index")
    assert gui.get("/api/models").status_code in (200, 401, 404)


def test_a15_an_oversized_message_is_refused_before_it_is_stored(tmp_path) -> None:
    wired = _wire(tmp_path, client_host="192.168.1.20")
    response = wired.client.post(
        f"/room/{wired.room.id}/messages",
        json={"content": "x" * (64 * 1024)},
        headers={**_auth(wired.token), "Idempotency-Key": "big"},
    )
    assert response.status_code == 413
    assert wired.rooms.messages_with_speaker(wired.room.id) == []


# --- A17: the rest of the product is untouched -----------------------------


def test_a17_a_room_created_without_the_switches_is_invisible(tmp_path) -> None:
    db = tmp_path / "lan.db"
    sessions = SessionStore(db)
    rooms = RoomStore(db, sessions)
    plain = rooms.create(name="Companion", character_ids=[7], agent_mode=True)
    assert plain.lan_enabled is False

    members = AgentMemberStore(db)
    members.add(plain.id, ref="probe", display_name="Probe")
    tokens = MemberTokenStore(db)
    issued = tokens.issue(plain.id, "probe")
    deps = RoomDeps(
        tokens=tokens, blocklist=LanBlocklist(db), audit=AuthAuditStore(db),
        rooms=rooms, members=members, budget=RateBudget(),
        idempotency=IdempotencyStore(db),
    )
    client = TestClient(create_room_app(deps), client=("192.168.1.20", 40000))
    assert client.get("/room/index", headers=_auth(issued.token)).status_code == 404


# --- A18 / A19: the document and the record --------------------------------


def test_a18_the_doc_lists_every_registered_path(tmp_path) -> None:
    app = create_room_app(_wire(tmp_path).deps)
    for route in app.routes:
        if getattr(route, "methods", None):
            assert route.path in agent_md(True), route.path


def test_a19_the_audit_never_holds_a_credential(tmp_path) -> None:
    wired = _wire(tmp_path, client_host="192.168.1.20")
    wired.client.get("/room/index")
    wired.client.get("/room/index", headers=_auth(wired.token))
    wired.client.get("/room/index", headers=_auth("not-a-token"))
    blob = json.dumps(wired.deps.audit.list(limit=100), ensure_ascii=False)
    assert wired.token not in blob
    assert "not-a-token" not in blob
    assert "Bearer" not in blob


def test_a19_the_audit_says_why_a_request_was_refused(tmp_path) -> None:
    """Precise reasons live here, not in the response — that is the point."""
    wired = _wire(tmp_path, client_host="192.168.1.20")
    wired.client.get("/room/index", headers=_auth(wired.token))
    elsewhere = TestClient(create_room_app(wired.deps), client=("10.0.0.9", 40000))
    elsewhere.get("/room/index", headers=_auth(wired.token))
    reasons = {row["reason"] for row in wired.deps.audit.list(limit=50)}
    assert "ip_mismatch" in reasons


def test_a19_a_blocked_address_is_refused_without_explaining_itself(
    tmp_path,
) -> None:
    wired = _wire(tmp_path)
    other = LanBlocklist(wired.deps.blocklist.db_path)
    other.add(STRANGER_IP, reason="noise")
    response = wired.client.get("/room/index", headers=_auth(wired.token))
    # Same answer as a bad credential: the blocklist is not observable.
    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"


def test_a19_a_blocked_address_cannot_reach_the_document(tmp_path) -> None:
    wired = _wire(tmp_path)
    LanBlocklist(wired.deps.blocklist.db_path).add(STRANGER_IP)
    assert wired.client.get(
        "/room/agent.md", headers=_auth(wired.token)
    ).status_code == 401


def test_the_guest_reading_the_doc_is_told_what_it_cannot_do(tmp_path) -> None:
    """The doc is the member's only briefing; the refusals have to be in it."""
    for phrase in ("401", "403", "404", "409", "413", "429"):
        assert phrase in agent_md(True), phrase

# SPDX-License-Identifier: MIT
"""An address change has to announce itself.

TOFU's failure mode is quiet: the member just cannot connect, which looks like
a network problem. This is what turns it into something the owner will see.
"""

from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from src.memory.agent_members import AgentMemberStore
from src.memory.auth_audit import AuthAuditStore
from src.memory.lan_blocklist import LanBlocklist
from src.memory.member_tokens import MemberTokenStore
from src.memory.rooms import RoomStore
from src.memory.session_store import SessionStore
from src.security.rate_budget import RateBudget
from src.server.room_app import RoomDeps, create_room_app

ANCHOR_IP = "192.168.1.20"
OTHER_IP = "10.0.0.9"


def _wire(tmp_path, *, client_host: str = ANCHOR_IP):
    db = tmp_path / "lan.db"
    sessions = SessionStore(db)
    rooms = RoomStore(db, sessions)
    members = AgentMemberStore(db)
    tokens = MemberTokenStore(db)
    room = rooms.create(name="Work", character_ids=[], agent_mode=True,
                        lan_enabled=True)
    members.add(room.id, ref="claude-laptop", display_name="Claude")
    issued = tokens.issue(room.id, "claude-laptop")

    alerts: list[tuple[str, str, str]] = []
    deps = RoomDeps(
        tokens=tokens, blocklist=LanBlocklist(db), audit=AuthAuditStore(db),
        rooms=rooms, members=members, budget=RateBudget(),
        notify=lambda title, body, ref: alerts.append((title, body, ref)),
    )
    return SimpleNamespace(
        client=TestClient(create_room_app(deps), client=(client_host, 40000)),
        deps=deps, token=issued.token, token_id=issued.token_id,
        room=room, alerts=alerts,
    )


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _from_elsewhere(deps, ip: str = OTHER_IP) -> TestClient:
    """A second client: a client's source address is fixed at construction, so
    "the member moved" means a new client over the same stores."""
    return TestClient(create_room_app(deps), client=(ip, 40000))


def test_the_first_connection_anchors_without_an_alert(tmp_path) -> None:
    wired = _wire(tmp_path)
    assert wired.client.get(
        "/room/index", headers=_auth(wired.token)
    ).status_code == 200
    assert wired.alerts == []


def test_an_address_change_raises_one_alert(tmp_path) -> None:
    wired = _wire(tmp_path)
    assert wired.client.get(
        "/room/index", headers=_auth(wired.token)
    ).status_code == 200
    assert _from_elsewhere(wired.deps).get(
        "/room/index", headers=_auth(wired.token)
    ).status_code == 401
    assert len(wired.alerts) == 1
    title, body, ref = wired.alerts[0]
    combined = f"{title}\n{body}"
    assert ANCHOR_IP in combined
    assert OTHER_IP in combined
    # Named the way the owner knows it, not just by the internal ref.
    assert "Claude" in combined
    assert "claude-laptop" in combined
    assert ref == f"lan-ip-mismatch:{wired.token_id}:{OTHER_IP}"


def test_a_second_attempt_from_the_same_wrong_address_does_not_spam(
    tmp_path,
) -> None:
    wired = _wire(tmp_path)
    wired.client.get("/room/index", headers=_auth(wired.token))
    intruder = _from_elsewhere(wired.deps)
    for _ in range(5):
        intruder.get("/room/index", headers=_auth(wired.token))
    assert len(wired.alerts) == 1


def test_the_alert_body_carries_no_credential(tmp_path) -> None:
    wired = _wire(tmp_path)
    wired.client.get("/room/index", headers=_auth(wired.token))
    _from_elsewhere(wired.deps).get("/room/index", headers=_auth(wired.token))
    for _title, body, ref in wired.alerts:
        assert wired.token not in body
        assert wired.token not in ref
        assert "Bearer" not in body


def test_a_bad_token_raises_no_alert(tmp_path) -> None:
    """Only an address change is alarming; a stranger guessing credentials is
    noise, and an alert per guess would be a denial of service on the owner."""
    wired = _wire(tmp_path)
    wired.client.get("/room/index", headers=_auth("not-a-token"))
    assert wired.alerts == []


def test_an_expired_token_raises_no_alert(tmp_path) -> None:
    wired = _wire(tmp_path)
    tokens = MemberTokenStore(str(tmp_path / "lan.db"))
    rows = tokens.list_for(wired.room.id, "claude-laptop")
    tokens.revoke(int(rows[0]["id"]))
    wired.client.get("/room/index", headers=_auth(wired.token))
    assert wired.alerts == []


def test_a_disabled_notifier_does_not_break_the_refusal(tmp_path) -> None:
    wired = _wire(tmp_path)
    wired.client.get("/room/index", headers=_auth(wired.token))
    wired.deps.notify = None
    assert _from_elsewhere(wired.deps).get(
        "/room/index", headers=_auth(wired.token)
    ).status_code == 401


def test_a_raising_notifier_does_not_break_the_refusal(tmp_path) -> None:
    """An alert is best effort; it must never turn a refusal into a 500."""
    wired = _wire(tmp_path)
    wired.client.get("/room/index", headers=_auth(wired.token))

    def explode(_title, _body, _ref):
        raise RuntimeError("notification store is down")

    wired.deps.notify = explode
    assert _from_elsewhere(wired.deps).get(
        "/room/index", headers=_auth(wired.token)
    ).status_code == 401


def test_a_rebound_address_recovers_and_alerts_nothing(tmp_path) -> None:
    wired = _wire(tmp_path)
    wired.client.get("/room/index", headers=_auth(wired.token))
    tokens = MemberTokenStore(str(tmp_path / "lan.db"))
    tokens.rebind_ip(wired.token_id, OTHER_IP)
    assert _from_elsewhere(wired.deps).get(
        "/room/index", headers=_auth(wired.token)
    ).status_code == 200
    assert wired.alerts == []

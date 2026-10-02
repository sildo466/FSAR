# SPDX-License-Identifier: MIT
"""POST /room/{room_id}/patches — work coming back, waiting to be looked at."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.memory.agent_members import AgentMemberStore
from src.memory.auth_audit import AuthAuditStore
from src.memory.idempotency import IdempotencyStore
from src.memory.lan_blocklist import LanBlocklist
from src.memory.member_tokens import MemberTokenStore
from src.memory.patches import PatchStore
from src.memory.rooms import RoomStore
from src.memory.session_store import SessionStore
from src.security.rate_budget import RateBudget
from src.server.room_app import RoomDeps, create_room_app

PATCH = (
    "diff --git a/app.py b/app.py\n"
    "--- a/app.py\n"
    "+++ b/app.py\n"
    "@@ -1,1 +1,1 @@\n-x = 1\n+x = 2\n"
)


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("FSAR_HOME", str(tmp_path / "home"))


def _wire(tmp_path):
    db = tmp_path / "lan.db"
    sessions = SessionStore(db)
    rooms = RoomStore(db, sessions)
    members = AgentMemberStore(db)
    tokens = MemberTokenStore(db)
    patches = PatchStore(db)
    room = rooms.create(name="Work", character_ids=[], agent_mode=True,
                        lan_enabled=True)
    members.add(room.id, ref="claude-laptop", display_name="Claude")
    issued = tokens.issue(room.id, "claude-laptop")
    deps = RoomDeps(
        tokens=tokens, blocklist=LanBlocklist(db), audit=AuthAuditStore(db),
        rooms=rooms, members=members, budget=RateBudget(),
        idempotency=IdempotencyStore(db), patches=patches,
    )
    return SimpleNamespace(
        client=TestClient(create_room_app(deps), client=("192.168.1.20", 40000)),
        token=issued.token, room=room, rooms=rooms, members=members,
        patches=patches,
    )


def _post(wired, body, *, key="k1", token=None):
    headers = {"Authorization": f"Bearer {token or wired.token}"}
    if key is not None:
        headers["Idempotency-Key"] = key
    return wired.client.post(
        f"/room/{wired.room.id}/patches", json=body, headers=headers,
    )


def test_a_patch_waits_in_the_queue(tmp_path) -> None:
    wired = _wire(tmp_path)

    response = _post(wired, {"patch": PATCH, "item_key": "parse"})

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "pending"
    queued = wired.patches.list(wired.room.id)
    assert [p.id for p in queued] == [body["patch_id"]]
    assert queued[0].item_key == "parse"


def test_a_replayed_request_queues_nothing_extra(tmp_path) -> None:
    wired = _wire(tmp_path)
    first = _post(wired, {"patch": PATCH})

    second = _post(wired, {"patch": PATCH})

    assert second.json() == first.json()
    assert len(wired.patches.list(wired.room.id)) == 1


def test_the_same_patch_under_a_new_key_still_queues_once(tmp_path) -> None:
    wired = _wire(tmp_path)
    _post(wired, {"patch": PATCH}, key="k1")

    _post(wired, {"patch": PATCH}, key="k2")

    assert len(wired.patches.list(wired.room.id)) == 1


def test_a_malformed_patch_is_refused(tmp_path) -> None:
    wired = _wire(tmp_path)

    response = _post(wired, {"patch": "please apply this"})

    assert response.status_code == 400
    assert response.json()["code"] == "bad_patch"
    assert wired.patches.list(wired.room.id) == []


def test_a_refused_patch_says_which_shape_was_wrong(tmp_path) -> None:
    """bad_patch alone leaves the sender guessing between binary, mode change,
    submodule and "not a diff at all"."""
    wired = _wire(tmp_path)
    body = _post(wired, {"patch": "please apply this"}).json()
    assert body["code"] == "bad_patch"
    assert "not a git diff" in body["reason"]


def test_a_patch_that_is_not_a_string_is_refused(tmp_path) -> None:
    wired = _wire(tmp_path)
    response = _post(wired, {"patch": 123})
    assert response.status_code == 400
    assert response.json()["code"] == "bad_patch"


def test_an_unknown_field_is_refused(tmp_path) -> None:
    wired = _wire(tmp_path)
    response = _post(wired, {"patch": PATCH, "room_id": 9})
    assert response.status_code == 400
    assert response.json()["code"] == "unknown_field"


def test_a_missing_idempotency_key_is_refused(tmp_path) -> None:
    wired = _wire(tmp_path)
    response = _post(wired, {"patch": PATCH}, key=None)
    assert response.status_code == 400
    assert response.json()["code"] == "idempotency_key_required"


def test_a_patch_needs_a_token(tmp_path) -> None:
    wired = _wire(tmp_path)
    response = wired.client.post(
        f"/room/{wired.room.id}/patches", json={"patch": PATCH},
        headers={"Idempotency-Key": "k1"},
    )
    assert response.status_code == 401


def test_a_room_with_lan_off_is_404(tmp_path) -> None:
    wired = _wire(tmp_path)
    wired.rooms.update(wired.room.id, lan_enabled=False)
    assert _post(wired, {"patch": PATCH}).status_code == 404


def test_a_removed_member_is_404(tmp_path) -> None:
    wired = _wire(tmp_path)
    wired.members.remove(wired.room.id, "claude-laptop")
    assert _post(wired, {"patch": PATCH}).status_code == 404


def test_a_posted_patch_is_visible_in_state(tmp_path) -> None:
    """A sender closes the loop by polling state, so the patch it just queued
    has to be there — otherwise patch_id buys it nothing."""
    wired = _wire(tmp_path)
    posted = _post(wired, {"patch": PATCH, "item_key": "parse"}).json()

    state = wired.client.get(
        f"/room/{wired.room.id}/state?since=0",
        headers={"Authorization": f"Bearer {wired.token}"},
    ).json()
    by_id = {p["patch_id"]: p for p in state["patches"]}
    assert by_id[posted["patch_id"]]["state"] == "pending"
    assert by_id[posted["patch_id"]]["item_key"] == "parse"
    assert by_id[posted["patch_id"]]["member_ref"] == "claude-laptop"

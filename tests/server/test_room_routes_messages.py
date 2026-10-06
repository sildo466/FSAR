# SPDX-License-Identifier: MIT
"""POST /room/{room_id}/messages — the one thing a member can actually do."""

from __future__ import annotations

import time
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
from src.security.visitor_screen import VisitorVerdict
from src.server import room_app as room_app_module
from src.server.handlers import group as group_handler
from src.server.room_app import RoomDeps, create_room_app


@pytest.fixture()
def wired(tmp_path, monkeypatch):
    db = tmp_path / "lan.db"
    sessions = SessionStore(db)
    rooms = RoomStore(db, sessions)
    members = AgentMemberStore(db)
    tokens = MemberTokenStore(db)
    room = rooms.create(name="Work", character_ids=[], agent_mode=True,
                        lan_enabled=True)
    members.add(room.id, ref="claude-laptop", display_name="Claude")
    issued = tokens.issue(room.id, "claude-laptop")

    posts: list[dict] = []

    async def fake_post(*, room_id, member_ref, content, ws=None):
        posts.append(
            {"room_id": room_id, "member_ref": member_ref, "content": content}
        )
        return {"ok": True, "code": "ok", "row_id": 42}

    monkeypatch.setattr(group_handler, "post_member_message", fake_post)

    deps = RoomDeps(
        tokens=tokens, blocklist=LanBlocklist(db), audit=AuthAuditStore(db),
        rooms=rooms, members=members, budget=RateBudget(),
        idempotency=IdempotencyStore(db),
    )
    return SimpleNamespace(
        client=TestClient(create_room_app(deps), client=("192.168.1.20", 40000)),
        token=issued.token, room=room, rooms=rooms, members=members,
        tokens=tokens, deps=deps, posts=posts,
    )


def _headers(token: str, key: str = "k-1") -> dict:
    return {"Authorization": f"Bearer {token}", "Idempotency-Key": key}


def _post(wired, content: str = "hello room", key: str = "k-1"):
    return wired.client.post(
        f"/room/{wired.room.id}/messages", json={"content": content},
        headers=_headers(wired.token, key),
    )


def test_a_message_reaches_the_shared_entry_point(wired) -> None:
    response = _post(wired)
    assert response.status_code == 200
    assert response.json() == {"row_id": 42}
    assert wired.posts == [
        {"room_id": wired.room.id, "member_ref": "claude-laptop",
         "content": "hello room"},
    ]


def test_a_missing_idempotency_key_is_refused(wired) -> None:
    response = wired.client.post(
        f"/room/{wired.room.id}/messages", json={"content": "hi"},
        headers={"Authorization": f"Bearer {wired.token}"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "idempotency_key_required"
    assert wired.posts == []


def test_a_replayed_key_does_not_post_twice(wired) -> None:
    first = _post(wired, content="hi", key="same-key")
    second = _post(wired, content="hi", key="same-key")
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == first.json()
    assert len(wired.posts) == 1


def test_the_same_key_with_other_content_conflicts(wired) -> None:
    _post(wired, content="first", key="same-key")
    response = _post(wired, content="second", key="same-key")
    assert response.status_code == 409
    assert response.json()["code"] == "idempotency_conflict"
    assert len(wired.posts) == 1


def test_a_different_key_posts_again(wired) -> None:
    _post(wired, content="hi", key="one")
    _post(wired, content="hi", key="two")
    assert len(wired.posts) == 2


def test_an_unknown_body_field_is_refused(wired) -> None:
    response = wired.client.post(
        f"/room/{wired.room.id}/messages",
        json={"content": "hi", "room_id": 999, "member_ref": "someone-else"},
        headers=_headers(wired.token),
    )
    assert response.status_code == 400
    assert response.json()["code"] == "unknown_field"
    assert wired.posts == []


def test_a_duplicate_json_key_is_refused(wired) -> None:
    response = wired.client.post(
        f"/room/{wired.room.id}/messages",
        content='{"content": "a", "content": "b"}',
        headers={**_headers(wired.token), "Content-Type": "application/json"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "duplicate_key"
    assert wired.posts == []


def test_the_body_cannot_redirect_the_room(wired) -> None:
    _post(wired)
    assert wired.posts[0]["room_id"] == wired.room.id
    assert wired.posts[0]["member_ref"] == "claude-laptop"


def test_oversized_content_is_413(wired) -> None:
    response = _post(wired, content="x" * (16 * 1024 + 1))
    assert response.status_code == 413
    assert wired.posts == []


def test_multibyte_content_is_measured_in_bytes(wired) -> None:
    # 9000 three-byte characters is 27 KiB of UTF-8.
    response = _post(wired, content="あ" * 9000)
    assert response.status_code == 413


@pytest.mark.parametrize("payload", [123, None, True, ["hi"], {"a": 1}])
def test_a_content_that_is_not_a_string_is_refused(wired, payload) -> None:
    """str() used to be applied to whatever arrived, so {"content": 123} came
    back 200 and "123" was said in the room."""
    response = wired.client.post(
        f"/room/{wired.room.id}/messages", json={"content": payload},
        headers=_headers(wired.token),
    )
    assert response.status_code == 400
    assert response.json()["code"] == "bad_content"
    assert wired.posts == []


def test_an_oversized_body_is_stopped_while_it_is_read(wired, monkeypatch) -> None:
    """The cap has to apply to the read, not to a body already in memory."""
    monkeypatch.setattr(room_app_module, "MAX_BODY_BYTES", 200)
    response = wired.client.post(
        f"/room/{wired.room.id}/messages",
        content='{"content": "' + "x" * 500 + '"}',
        headers={**_headers(wired.token), "Content-Type": "application/json"},
    )
    assert response.status_code == 413
    assert response.json()["code"] == "too_long"
    assert wired.posts == []


def test_a_refused_payload_does_not_spend_the_allowance(wired, monkeypatch) -> None:
    """The budget bounds what reaches the room, so a request the room never
    saw must not draw on it — otherwise retrying a mangled body locks the
    caller out of the send that was fine."""
    monkeypatch.setattr(room_app_module, "SPEAK_BUDGET", (1, 60.0, 1))
    bad = wired.client.post(
        f"/room/{wired.room.id}/messages",
        json={"content": "hi", "room_id": 999},
        headers=_headers(wired.token, "bad"),
    )
    assert bad.status_code == 400
    assert bad.json()["code"] == "unknown_field"
    assert _post(wired, content="hi", key="good").status_code == 200


def test_a_muted_member_is_403(wired, monkeypatch) -> None:
    async def muted_post(*, room_id, member_ref, content, ws=None):
        return {"ok": False, "code": "muted", "row_id": None}

    monkeypatch.setattr(group_handler, "post_member_message", muted_post)
    response = _post(wired)
    assert response.status_code == 403
    assert response.json()["code"] == "muted"


def test_an_empty_message_is_400(wired, monkeypatch) -> None:
    async def empty_post(*, room_id, member_ref, content, ws=None):
        return {"ok": False, "code": "empty", "row_id": None}

    monkeypatch.setattr(group_handler, "post_member_message", empty_post)
    response = _post(wired, content="   ")
    assert response.status_code == 400
    assert response.json()["code"] == "empty"


def test_an_unwired_room_becomes_503(wired, monkeypatch) -> None:
    async def unwired_post(*, room_id, member_ref, content, ws=None):
        return {"ok": False, "code": "not_ready", "row_id": None}

    monkeypatch.setattr(group_handler, "post_member_message", unwired_post)
    assert _post(wired).status_code == 503


def test_a_removed_member_cannot_speak(wired) -> None:
    wired.members.remove(wired.room.id, "claude-laptop")
    assert _post(wired).status_code == 404
    assert wired.posts == []


def test_a_revoked_token_cannot_replay_a_cached_answer(wired) -> None:
    """Authorization runs before the cache: a revoked credential must not read
    an answer it earned while it was still valid."""
    _post(wired, content="hi", key="replay-me")
    rows = wired.tokens.list_for(wired.room.id, "claude-laptop")
    wired.tokens.revoke(int(rows[0]["id"]))
    response = _post(wired, content="hi", key="replay-me")
    assert response.status_code == 401


def test_speaking_needs_a_token(wired) -> None:
    assert wired.client.post(
        f"/room/{wired.room.id}/messages", json={"content": "hi"},
    ).status_code == 401


def test_speaking_is_rate_limited_per_member(wired, monkeypatch) -> None:
    monkeypatch.setattr(room_app_module, "SPEAK_BUDGET", (2, 60.0, 2))
    codes = [_post(wired, content="hi", key=f"key-{i}").status_code for i in range(3)]
    assert codes == [200, 200, 429]


def test_speaking_is_rate_limited_per_room(wired, monkeypatch) -> None:
    monkeypatch.setattr(room_app_module, "ROOM_SPEAK_BUDGET", (1, 60.0, 1))
    first = _post(wired, content="a", key="a")
    second = _post(wired, content="b", key="b")
    assert (first.status_code, second.status_code) == (200, 429)


def test_a_rate_limited_post_does_not_poison_the_key(wired, monkeypatch) -> None:
    """A 429 must not be stored under the key: the retry the client is about to
    make has to reach the room, not replay a refusal as a success."""
    monkeypatch.setattr(room_app_module, "SPEAK_BUDGET", (1, 0.2, 1))
    assert _post(wired, content="hi", key="same").status_code == 200
    assert _post(wired, content="hi", key="same").status_code == 429
    time.sleep(0.25)  # the bucket refills at five per second
    retry = _post(wired, content="hi", key="same")
    assert retry.status_code == 200
    assert retry.json() == {"row_id": 42}
    assert len(wired.posts) == 1


def test_a_foreign_room_is_404(wired) -> None:
    response = wired.client.post(
        "/room/99999/messages", json={"content": "hi"},
        headers=_headers(wired.token),
    )
    assert response.status_code == 404
    assert wired.posts == []


def test_the_speech_is_audited_without_the_credential(wired) -> None:
    _post(wired)
    import json

    blob = json.dumps(wired.deps.audit.list(limit=50), ensure_ascii=False)
    assert "lan_message" in blob
    assert wired.token not in blob


# --- the visitor screen -----------------------------------------------------


class _Screen:
    """Stands in for the judge, so what is under test is what the route does
    with a verdict rather than how the verdict was reached."""

    def __init__(self, verdict: VisitorVerdict) -> None:
        self.verdict = verdict
        self.seen: list[str] = []

    def screen(self, text: str) -> VisitorVerdict:
        self.seen.append(text)
        return self.verdict


def _flagged() -> VisitorVerdict:
    return VisitorVerdict(flagged=True, category="abuse", confidence=0.95,
                          route="llm", reason="calls the owner worthless")


def test_a_flagged_line_is_refused_and_bans_the_credential(wired) -> None:
    notes: list[tuple[str, str, str]] = []
    wired.deps.visitor_screen = _Screen(_flagged())
    wired.deps.notify = lambda title, body, ref: notes.append((title, body, ref))

    response = _post(wired)

    assert response.status_code == 403
    assert response.json()["code"] == "banned"
    assert wired.posts == [], "the line must not reach the room"
    record = wired.tokens.resolve_record(wired.token)
    assert record.banned_at is not None
    assert record.banned_reason == "abuse"
    assert record.revoked_at is None, "a ban is not a revoke"
    assert len(notes) == 1
    assert "abuse" in notes[0][1]
    assert "hello room" in notes[0][1], "the owner has to see what was said"


def test_a_ban_closes_every_route_at_once(wired) -> None:
    wired.deps.visitor_screen = _Screen(_flagged())
    assert _post(wired).status_code == 403
    assert wired.client.get(
        f"/room/{wired.room.id}/state?since=0",
        headers={"Authorization": f"Bearer {wired.token}"},
    ).status_code == 401


def test_a_line_the_screen_clears_is_posted(wired) -> None:
    wired.deps.visitor_screen = _Screen(VisitorVerdict(route="clear"))
    assert _post(wired).status_code == 200
    assert len(wired.posts) == 1


def test_a_replay_is_not_screened_again(wired) -> None:
    screen = _Screen(VisitorVerdict(route="clear"))
    wired.deps.visitor_screen = screen
    _post(wired, content="hi", key="same")
    _post(wired, content="hi", key="same")
    assert screen.seen == ["hi"]


def test_a_rate_limited_post_is_never_screened(wired, monkeypatch) -> None:
    """The screen is the expensive step, so it sits behind the budget: a caller
    that is already over its rate must not be able to spend model calls."""
    monkeypatch.setattr(room_app_module, "SPEAK_BUDGET", (1, 60.0, 1))
    screen = _Screen(VisitorVerdict(route="clear"))
    wired.deps.visitor_screen = screen
    assert _post(wired, content="one", key="one").status_code == 200
    assert _post(wired, content="two", key="two").status_code == 429
    assert screen.seen == ["one"]

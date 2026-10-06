# SPDX-License-Identifier: MIT
"""GET /room/{room_id}/state — messages after a cursor, and nothing else."""

from __future__ import annotations

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


def _wire(tmp_path, *, history_limit: int = 100, plans=None):
    db = tmp_path / "lan.db"
    sessions = SessionStore(db)
    rooms = RoomStore(db, sessions)
    members = AgentMemberStore(db)
    tokens = MemberTokenStore(db)
    room = rooms.create(name="Work", character_ids=[], agent_mode=True,
                        lan_enabled=True)
    members.add(room.id, ref="claude-laptop", display_name="Claude")
    issued = tokens.issue(room.id, "claude-laptop")
    cards = SimpleNamespace(
        get_character=lambda cid: (
            SimpleNamespace(id=cid, name="Mira") if cid == 7 else None
        ),
        get_user_card=lambda cid: None,
        get_default_user_card=lambda: SimpleNamespace(name="You"),
    )
    deps = RoomDeps(
        tokens=tokens, blocklist=LanBlocklist(db), audit=AuthAuditStore(db),
        rooms=rooms, members=members, budget=RateBudget(), cards=cards,
        history_limit=history_limit, plans=plans,
    )
    return SimpleNamespace(
        client=TestClient(create_room_app(deps), client=("192.168.1.20", 40000)),
        token=issued.token, room=room, sessions=sessions, rooms=rooms,
        members=members, deps=deps,
    )


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _state(wired, query: str = "?since=0"):
    return wired.client.get(
        f"/room/{wired.room.id}/state{query}", headers=_auth(wired.token)
    )


def test_state_returns_the_rooms_messages(tmp_path) -> None:
    wired = _wire(tmp_path)
    wired.sessions.append_message(wired.room.session_id, "user", "hello")
    body = _state(wired).json()
    assert body["room_name"] == "Work"
    assert body["member_ref"] == "claude-laptop"
    assert [message["content"] for message in body["messages"]] == ["hello"]


def test_the_projection_is_exactly_what_p2_promises(tmp_path) -> None:
    """No phase, no plan items, no history range: none of those exist yet, and
    a field that always comes back empty reads like a promise."""
    wired = _wire(tmp_path)
    wired.sessions.append_message(wired.room.session_id, "user", "hello")
    body = _state(wired).json()
    assert set(body) == {
        "room_id", "room_name", "member_ref", "next_since", "truncated",
        "messages",
    }
    assert set(body["messages"][0]) == {
        "row_id", "role", "speaker_name", "speaker_kind", "content",
        "created_at",
    }


def test_a_room_with_a_board_gets_the_board(tmp_path) -> None:
    from src.memory.room_plan import RoomPlanStore

    plans = RoomPlanStore(tmp_path / "lan.db")
    wired = _wire(tmp_path, plans=plans)
    plans.replace(wired.room.id, [{
        "id": "a", "text": "parse the config", "status": "todo",
        "owner": {"kind": "character", "ref": "7"},
    }])
    wired.sessions.append_message(wired.room.session_id, "user", "hello")

    body = _state(wired).json()

    assert body["plan"] == [{
        "item_key": "a", "text": "parse the config", "status": "todo",
        "owner_kind": "character",
    }]


def test_a_room_without_a_board_gets_no_key_at_all(tmp_path) -> None:
    """Not an empty array: absent. The absence is what the member reads."""
    wired = _wire(tmp_path)
    wired.sessions.append_message(wired.room.session_id, "user", "hello")
    assert "plan" not in _state(wired).json()


def test_names_resolve_for_every_speaker_kind(tmp_path) -> None:
    wired = _wire(tmp_path)
    wired.sessions.append_message(wired.room.session_id, "user", "hello")
    wired.sessions.append_message(
        wired.room.session_id, "assistant", "on it",
        speaker_kind="agent", speaker_ref="claude-laptop",
    )
    wired.sessions.append_message(
        wired.room.session_id, "assistant", "hi", character_card_id=7,
    )
    names = [message["speaker_name"] for message in _state(wired).json()["messages"]]
    assert names == ["You", "Claude", "Mira"]


def test_a_deleted_character_is_named_rather_than_dropped(tmp_path) -> None:
    wired = _wire(tmp_path)
    wired.sessions.append_message(
        wired.room.session_id, "assistant", "gone", character_card_id=99,
    )
    assert _state(wired).json()["messages"][0]["speaker_name"] == "Unknown"


def test_an_agent_row_with_no_speaker_kind_is_not_special_cased(tmp_path) -> None:
    """P1 rows have speaker_kind NULL; they must fall through to card naming."""
    wired = _wire(tmp_path)
    wired.sessions.append_message(
        wired.room.session_id, "assistant", "hi", character_card_id=7,
    )
    message = _state(wired).json()["messages"][0]
    assert message["speaker_kind"] is None
    assert message["speaker_name"] == "Mira"


def test_the_cursor_skips_what_the_member_has_seen(tmp_path) -> None:
    wired = _wire(tmp_path)
    first = wired.sessions.append_message(wired.room.session_id, "user", "one")
    wired.sessions.append_message(wired.room.session_id, "user", "two")
    body = _state(wired, f"?since={first}").json()
    assert [message["content"] for message in body["messages"]] == ["two"]
    assert body["next_since"] > first


def test_a_full_page_reports_truncation(tmp_path) -> None:
    wired = _wire(tmp_path, history_limit=2)
    for text in ("one", "two", "three"):
        wired.sessions.append_message(wired.room.session_id, "user", text)
    body = _state(wired).json()
    assert len(body["messages"]) == 2
    assert body["truncated"] is True


def test_a_partial_page_is_not_truncated(tmp_path) -> None:
    wired = _wire(tmp_path, history_limit=10)
    wired.sessions.append_message(wired.room.session_id, "user", "only")
    body = _state(wired).json()
    assert body["truncated"] is False
    assert body["next_since"] > 0


def test_an_empty_room_returns_the_cursor_it_was_given(tmp_path) -> None:
    wired = _wire(tmp_path)
    body = _state(wired, "?since=17").json()
    assert body["messages"] == []
    assert body["next_since"] == 17


def test_a_missing_cursor_is_refused(tmp_path) -> None:
    """Absent used to mean 0, so one request could read out a whole room and
    look like a normal answer."""
    wired = _wire(tmp_path)
    wired.sessions.append_message(wired.room.session_id, "user", "hello")
    response = _state(wired, "")
    assert response.status_code == 400
    assert response.json()["code"] == "since_required"


def test_a_negative_cursor_is_refused(tmp_path) -> None:
    wired = _wire(tmp_path)
    wired.sessions.append_message(wired.room.session_id, "user", "hello")
    response = _state(wired, "?since=-5")
    assert response.status_code == 400
    assert response.json()["code"] == "bad_since"


def test_a_non_numeric_cursor_is_a_uniform_400(tmp_path) -> None:
    """Not FastAPI's 422: that body names pydantic, its `loc` and its `input`,
    and it is the only reply on this surface shaped like that."""
    wired = _wire(tmp_path)
    response = _state(wired, "?since=abc")
    assert response.status_code == 400
    body = response.json()
    assert set(body) == {"code", "request_id"}
    assert body["code"] == "bad_since"


def test_a_non_numeric_room_id_is_a_uniform_400(tmp_path) -> None:
    wired = _wire(tmp_path)
    response = wired.client.get("/room/abc/state?since=0", headers=_auth(wired.token))
    assert response.status_code == 400
    assert response.json()["code"] == "bad_room_id"


def test_a_bad_room_id_is_not_answered_before_authentication(tmp_path) -> None:
    wired = _wire(tmp_path)
    assert wired.client.get("/room/abc/state?since=0").status_code == 401


def test_another_room_is_404(tmp_path) -> None:
    wired = _wire(tmp_path)
    response = wired.client.get(
        "/room/99999/state", headers=_auth(wired.token)
    )
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_a_room_with_lan_off_is_404(tmp_path) -> None:
    wired = _wire(tmp_path)
    wired.rooms.update(wired.room.id, lan_enabled=False)
    assert _state(wired).status_code == 404


def test_a_removed_member_is_404(tmp_path) -> None:
    wired = _wire(tmp_path)
    wired.members.remove(wired.room.id, "claude-laptop")
    assert _state(wired).status_code == 404


def test_state_needs_a_token(tmp_path) -> None:
    wired = _wire(tmp_path)
    assert wired.client.get(f"/room/{wired.room.id}/state").status_code == 401


def test_a_foreign_room_id_cannot_be_reached_by_the_body_or_query(tmp_path) -> None:
    wired = _wire(tmp_path)
    other = wired.rooms.create(name="Other", character_ids=[],
                               agent_mode=True, lan_enabled=True)
    assert wired.client.get(
        f"/room/{other.id}/state", headers=_auth(wired.token)
    ).status_code == 404

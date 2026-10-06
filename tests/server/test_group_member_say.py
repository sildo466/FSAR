# SPDX-License-Identifier: MIT
"""An external member posts a line; the characters answer it."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from src.server.handlers import group as group_handler


def _wire(*, state: str = "active", max_rounds: int = 0):
    chains: list[dict] = []

    async def fake_run_chain(ws, *, room, user_input, mentioned, user_card,
                             max_rounds_override=None):
        chains.append({
            "room_id": room.id, "ws": ws, "user_input": user_input,
            "mentioned": mentioned, "max_rounds_override": max_rounds_override,
        })
        return "settled"

    member = SimpleNamespace(ref="claude-laptop", display_name="Claude", state=state)
    agents = SimpleNamespace(
        members=lambda room_id: [member],
        get=lambda room_id, ref: member if ref == member.ref else None,
    )
    appended: list[dict] = []

    def append(conv, role, content, **kw):
        appended.append({"conv": conv, "role": role, "content": content, **kw})
        return 42

    chat = SimpleNamespace(
        session_store=SimpleNamespace(append_message=append),
        card_repo=SimpleNamespace(
            get_user_card=lambda cid: None,
            get_default_user_card=lambda: SimpleNamespace(name="You"),
        ),
    )
    room = SimpleNamespace(
        id=1, session_id="s1", user_card_id=None, max_rounds=max_rounds,
    )
    engine = SimpleNamespace(chat=chat, run_chain=fake_run_chain)
    rooms = SimpleNamespace(get=lambda room_id: room, members=lambda room_id: [7])
    group_handler.set_engine(engine, rooms, agents)
    group_handler._tasks.clear()
    return appended, chains


async def _post(**kwargs) -> dict:
    result = await group_handler.post_member_message(**kwargs)
    await asyncio.sleep(0)  # let the spawned chain task start
    return result


def test_active_member_message_is_stored_as_agent_speaker() -> None:
    appended, _ = _wire()
    result = asyncio.run(
        _post(room_id=1, member_ref="claude-laptop", content="hello room")
    )
    assert result == {"ok": True, "code": "ok", "row_id": 42}
    row = appended[0]
    assert row["conv"] == "s1"
    assert row["role"] == "assistant"
    assert row["speaker_kind"] == "agent"
    assert row["speaker_ref"] == "claude-laptop"
    assert row["content"] == "hello room"


def test_member_message_triggers_a_chain() -> None:
    _, chains = _wire()
    asyncio.run(_post(room_id=1, member_ref="claude-laptop", content="hello"))
    assert len(chains) == 1
    assert chains[0]["user_input"] == "hello"


def test_member_message_is_echoed_to_the_guis() -> None:
    sent: list[dict] = []

    class Sock:
        async def send_json(self, payload):
            sent.append(payload)

    _wire()
    asyncio.run(
        _post(room_id=1, member_ref="claude-laptop", content="hi", ws=Sock())
    )
    event = sent[0]
    assert event["type"] == "group.user_message"
    assert event["speaker_kind"] == "agent"
    assert event["member_ref"] == "claude-laptop"
    assert event["user_name"] == "Claude"
    assert event["content"] == "hi"


def test_free_speech_room_gets_a_round_cap() -> None:
    _, chains = _wire(max_rounds=0)
    asyncio.run(_post(room_id=1, member_ref="claude-laptop", content="hi"))
    assert chains[0]["max_rounds_override"] == group_handler.FREE_SPEECH_MAX_ROUNDS


def test_explicit_room_cap_is_left_alone() -> None:
    _, chains = _wire(max_rounds=9)
    asyncio.run(_post(room_id=1, member_ref="claude-laptop", content="hi"))
    assert chains[0]["max_rounds_override"] is None


def test_muted_member_is_rejected_and_nothing_is_stored() -> None:
    appended, chains = _wire(state="muted")
    result = asyncio.run(
        _post(room_id=1, member_ref="claude-laptop", content="let me in")
    )
    assert result == {"ok": False, "code": "muted", "row_id": None}
    assert appended == []
    assert chains == []


def test_unknown_member_is_rejected() -> None:
    _wire()
    result = asyncio.run(_post(room_id=1, member_ref="ghost", content="hi"))
    assert result == {"ok": False, "code": "no_member", "row_id": None}


def test_empty_content_is_rejected() -> None:
    appended, _ = _wire()
    result = asyncio.run(
        _post(room_id=1, member_ref="claude-laptop", content="   ")
    )
    assert result == {"ok": False, "code": "empty", "row_id": None}
    assert appended == []


def test_oversized_content_is_rejected() -> None:
    appended, _ = _wire()
    result = asyncio.run(
        _post(room_id=1, member_ref="claude-laptop", content="x" * (16 * 1024 + 1))
    )
    assert result == {"ok": False, "code": "too_long", "row_id": None}
    assert appended == []


def test_chain_receives_a_broadcast_socket_not_none() -> None:
    _, chains = _wire()
    asyncio.run(_post(room_id=1, member_ref="claude-laptop", content="hi"))
    assert chains[0]["ws"] is not None
    assert hasattr(chains[0]["ws"], "send_json")


def test_post_is_refused_before_the_stores_are_wired() -> None:
    _wire()
    group_handler.set_engine(SimpleNamespace(), SimpleNamespace())
    result = asyncio.run(_post(room_id=1, member_ref="claude-laptop", content="hi"))
    assert result == {"ok": False, "code": "not_ready", "row_id": None}


def test_member_say_message_type_routes_through_post() -> None:
    from src.server.handlers import group as gh

    appended, chains = _wire()

    class FakeWebSocket:
        def __init__(self) -> None:
            self.messages: list[dict] = []

        async def send_json(self, message: dict) -> None:
            self.messages.append(message)

    ws = FakeWebSocket()

    async def scenario() -> None:
        handled = await gh.dispatch(ws, {
            "type": "group.member.say", "room_id": 1,
            "member_ref": "claude-laptop", "content": "hi from ws",
        })
        assert handled is True
        await asyncio.sleep(0)

    asyncio.run(scenario())
    assert appended[0]["content"] == "hi from ws"
    assert len(chains) == 1


def test_member_say_message_type_reports_a_rejection() -> None:
    from src.server.handlers import group as gh

    _wire(state="muted")

    class FakeWebSocket:
        def __init__(self) -> None:
            self.messages: list[dict] = []

        async def send_json(self, message: dict) -> None:
            self.messages.append(message)

    ws = FakeWebSocket()
    asyncio.run(gh.dispatch(ws, {
        "type": "group.member.say", "room_id": 1,
        "member_ref": "claude-laptop", "content": "hi",
    }))
    assert ws.messages[-1]["type"] == "group.error"
    assert ws.messages[-1]["code"] == "muted"

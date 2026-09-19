# SPDX-License-Identifier: MIT
from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from src.memory.session_store import MessageRow
from src.server.handlers import group as group_handler


class FakeWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send_json(self, message: dict) -> None:
        self.messages.append(message)


def _room(room_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        id=room_id, name="Island", description="d", scenario_prompt="s",
        session_id="s1", user_card_id=2, pinned=False,
        to_dict=lambda: {
            "id": room_id, "name": "Island", "description": "d",
            "scenario_prompt": "s", "session_id": "s1", "user_card_id": 2,
            "pinned": False, "created_at": "", "updated_at": "",
        },
    )


def _rooms() -> SimpleNamespace:
    state: dict = {"members": [7]}
    return SimpleNamespace(
        state=state,
        list=lambda: [_room()],
        create=lambda **kw: (state.update(kw), _room())[1],
        get=lambda rid: _room() if rid == 1 else None,
        update=lambda rid, **kw: _room() if rid == 1 else None,
        delete=lambda rid: rid == 1,
        members=lambda rid: list(state["members"]),
        add_members=lambda rid, ids: state.update(
            members=list(dict.fromkeys(state["members"] + list(ids)))
        ),
        remove_member=lambda rid, cid: (
            state.update(members=[m for m in state["members"] if m != cid])
            or cid in state["members"] + [cid]
        ),
        messages_with_speaker=lambda rid: [
            MessageRow(id=11, session_id="s1", role="assistant",
                       content="hi", character_card_id=7),
        ],
        prune_missing_members=lambda: 0,
    )


def _chat() -> SimpleNamespace:
    appended: list[dict] = []
    rated: list[dict] = []
    chat = SimpleNamespace(appended=appended, rated=rated)
    def append_message(cid, role, content, **kw):
        appended.append({"conv": cid, "role": role, "content": content})
        return 900 + len(appended)

    chat.session_store = SimpleNamespace(append_message=append_message)
    chat.card_repo = SimpleNamespace(
        get_character=lambda cid: SimpleNamespace(id=cid, name=f"C{cid}"),
        get_user_card=lambda cid: None,
        get_default_user_card=lambda: SimpleNamespace(id=1, name="tester"),
    )
    chat._render_attachments = lambda files: (
        "\n\U0001f4ce " + ", ".join(Path(f).name for f in files), "[FILE BODY]"
    )
    chat.rate = lambda mid, score, reason="", session_id=None: (
        rated.append({"mid": mid, "score": score, "session_id": session_id})
        or {"status": "ok", "db_id": 11}
    )
    return chat


def _engine() -> SimpleNamespace:
    engine = SimpleNamespace()
    engine.chat = _chat()
    engine.cancelled: list[int] = []
    cancelled_set: set[int] = set()
    engine.cancel = lambda rid: (engine.cancelled.append(rid),
                                 cancelled_set.add(rid))
    engine.is_cancelled = lambda rid: rid in cancelled_set
    engine.regenerated: list[dict] = []
    chain_calls: list[dict] = []
    engine.chain_calls = chain_calls

    async def regenerate(ws, **kwargs):
        engine.regenerated.append(kwargs)
        return ("group_new", "new")

    engine.regenerate = regenerate

    async def run_chain(ws, **kwargs):
        chain_calls.append(kwargs)
        return "settled"

    engine.run_chain = run_chain
    return engine


def _setup(engine=None) -> tuple[SimpleNamespace, SimpleNamespace]:
    engine = engine or _engine()
    rooms = _rooms()
    group_handler._tasks.clear()
    group_handler.set_engine(engine, rooms)
    return engine, rooms


def _dispatch(ws, msg):
    return asyncio.run(group_handler.dispatch(ws, msg))


def test_dispatch_ignores_non_group_messages() -> None:
    _setup()
    assert _dispatch(FakeWebSocket(), {"type": "chat.send"}) is False


def test_group_list_returns_rooms_with_members() -> None:
    _setup()
    ws = FakeWebSocket()
    assert _dispatch(ws, {"type": "group.list"}) is True
    listed = next(m for m in ws.messages if m["type"] == "group.list.ok")
    assert listed["rooms"][0]["id"] == 1
    assert listed["rooms"][0]["members"] == [7]


def test_group_create_rejects_blank_name() -> None:
    _setup()
    ws = FakeWebSocket()
    _dispatch(ws, {"type": "group.create", "name": "  ", "character_ids": [1]})
    err = next(m for m in ws.messages if m["type"] == "group.error")
    assert err["code"] == "invalid_name"


def test_group_create_rejects_empty_members() -> None:
    _setup()
    ws = FakeWebSocket()
    _dispatch(ws, {"type": "group.create", "name": "R", "character_ids": []})
    err = next(m for m in ws.messages if m["type"] == "group.error")
    assert err["code"] == "no_members"


def test_group_create_emits_created() -> None:
    _, rooms = _setup()
    ws = FakeWebSocket()
    _dispatch(ws, {
        "type": "group.create", "name": "Island",
        "description": "d", "scenario_prompt": "s",
        "user_card_id": 2, "character_ids": [7, 8],
    })
    created = next(m for m in ws.messages if m["type"] == "group.created")
    assert created["room"]["id"] == 1
    assert created["room"]["members"] == [7]


def test_group_update_emits_updated() -> None:
    _setup()
    ws = FakeWebSocket()
    _dispatch(ws, {"type": "group.update", "room_id": 1, "pinned": True})
    assert any(m["type"] == "group.updated" for m in ws.messages)


def test_group_delete_cancels_then_emits_deleted() -> None:
    engine, _ = _setup()
    ws = FakeWebSocket()
    _dispatch(ws, {"type": "group.delete", "room_id": 1})
    assert engine.cancelled == [1]
    assert any(m["type"] == "group.deleted" for m in ws.messages)


def test_group_members_add_emits_updated() -> None:
    _, rooms = _setup()
    ws = FakeWebSocket()
    _dispatch(ws, {"type": "group.members.add", "room_id": 1,
                   "character_ids": [8, 9]})
    assert rooms.state["members"] == [7, 8, 9]
    assert any(m["type"] == "group.updated" for m in ws.messages)


def test_group_members_remove_emits_updated() -> None:
    _, rooms = _setup()
    ws = FakeWebSocket()
    _dispatch(ws, {"type": "group.members.remove", "room_id": 1,
                   "character_id": 7})
    assert rooms.state["members"] == []


def test_group_history_carries_row_id_and_speaker() -> None:
    _setup()
    ws = FakeWebSocket()
    _dispatch(ws, {"type": "group.history", "room_id": 1})
    history = next(m for m in ws.messages if m["type"] == "group.history.ok")
    message = history["messages"][0]
    assert message["id"] == "11"
    assert message["row_id"] == 11
    assert message["character_id"] == 7
    assert message["character_name"] == "C7"


def test_group_history_unknown_room_is_silent() -> None:
    _setup()
    ws = FakeWebSocket()
    assert _dispatch(ws, {"type": "group.history", "room_id": 99}) is True
    assert ws.messages == []


def test_group_send_rejects_room_without_members() -> None:
    _, rooms = _setup()
    rooms.state["members"] = []
    ws = FakeWebSocket()
    _dispatch(ws, {"type": "group.send", "room_id": 1, "content": "hi"})
    err = next(m for m in ws.messages if m["type"] == "group.error")
    assert err["code"] == "no_members"


def test_group_send_persists_user_message_and_starts_chain() -> None:
    engine, _ = _setup()
    ws = FakeWebSocket()
    _dispatch(ws, {"type": "group.send", "room_id": 1, "content": "hi"})

    assert engine.chat.appended == [{"conv": "s1", "role": "user",
                                     "content": "hi"}]
    assert engine.chain_calls[0]["user_input"] == "hi"
    assert engine.chain_calls[0]["room"].id == 1


def test_group_send_echoes_the_user_message() -> None:
    """Without the echo the user's own line only appeared after a reload:
    history is the only other source for it."""
    engine, _ = _setup()
    ws = FakeWebSocket()
    _dispatch(ws, {"type": "group.send", "room_id": 1, "content": "hi"})

    echo = next(m for m in ws.messages if m["type"] == "group.user_message")
    assert echo["content"] == "hi"
    assert echo["message_id"] == "901"
    assert echo["row_id"] == 901
    assert echo["room_id"] == 1


def test_group_send_forwards_mentions_and_attachment_body() -> None:
    engine, _ = _setup()
    ws = FakeWebSocket()
    _dispatch(ws, {
        "type": "group.send", "room_id": 1, "content": "look",
        "attached_files": ["C:/x/a.txt"],
        "mentioned_character_ids": [8],
    })

    assert engine.chain_calls[0]["mentioned"] == [8]
    # The stored row keeps the marker only; the model sees the body.
    assert engine.chat.appended[0]["content"] == "look\n\U0001f4ce a.txt"
    assert "[FILE BODY]" in engine.chain_calls[0]["user_input"]
    assert engine.chain_calls[0]["user_input"].startswith("look\n\U0001f4ce a.txt")


def test_group_cancel_marks_room() -> None:
    engine, _ = _setup()
    _dispatch(FakeWebSocket(), {"type": "group.cancel", "room_id": 1})
    assert engine.cancelled == [1]


def test_group_rate_uses_room_session() -> None:
    engine, _ = _setup()
    ws = FakeWebSocket()
    _dispatch(ws, {"type": "group.rate", "room_id": 1,
                   "message_id": 11, "score": 5, "reason": "nice"})
    assert engine.chat.rated == [{"mid": "11", "score": 5,
                                 "session_id": "s1"}]
    assert any(m["type"] == "group.rate.ack" for m in ws.messages)


def test_group_regenerate_is_detached_and_forwards_row_id() -> None:
    """It must not be awaited in the handler, or the receive loop would be
    blocked for the whole stream and group.cancel could not interrupt it."""
    engine, _ = _setup()
    ws = FakeWebSocket()

    async def run():
        await group_handler.dispatch(
            ws, {"type": "group.regenerate", "room_id": 1, "message_id": 11}
        )
        task = group_handler._tasks.get(1)
        assert task is not None, "regenerate should be started as a task"
        await task

    asyncio.run(run())

    assert engine.regenerated[0]["message_row_id"] == 11


def test_group_error_is_reported_not_raised() -> None:
    engine, rooms = _setup()

    def boom(room_id):
        raise RuntimeError("db down")

    rooms.members = boom
    ws = FakeWebSocket()
    assert _dispatch(ws, {"type": "group.send", "room_id": 1,
                          "content": "hi"}) is True
    err = next(m for m in ws.messages if m["type"] == "group.error")
    assert err["code"] == "group_handler"
    assert "db down" in err["message"]

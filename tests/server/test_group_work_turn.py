# SPDX-License-Identifier: MIT
"""A work turn: the same character loop, pointed at one plan item."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from src.core.agent_runtime import AgentLoopResult
from src.memory.cards import CharacterCard
from src.server.group_engine import GroupEngine


class _WS:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)


def _mira() -> CharacterCard:
    return CharacterCard(id=7, name="Mira", description="witch", personality="calm")


def _room(**overrides) -> SimpleNamespace:
    base = {"id": 1, "session_id": "s1", "scenario_prompt": "", "name": "R",
            "user_card_id": None, "max_rounds": 0, "agent_mode": True}
    base.update(overrides)
    return SimpleNamespace(**base)


def _chat(captured: dict, *, conclusion="done", outcome="success"):
    chat = SimpleNamespace()
    chat.session_store = SimpleNamespace(get_session_messages=lambda cid, **kw: [])
    chat.card_repo = SimpleNamespace(get_character=lambda cid: _mira())
    chat._msg_ids = {}
    chat._short_cache = {}
    chat.client_and_model = lambda: (object(), "model", "provider")

    async def fake(ws, message_id, client, model, conv_id, user_input,
                   character=None, char_name=None, provider_id="", **kw):
        captured.update(kw)
        captured["user_input"] = user_input
        captured["message_id"] = message_id
        return AgentLoopResult(conclusion, outcome)

    chat._run_agent = fake
    return chat


def _engine(chat) -> GroupEngine:
    return GroupEngine(chat, SimpleNamespace(members=lambda room_id: [7]))


def _item(**over) -> SimpleNamespace:
    base = {"item_key": "a", "text": "parse the config", "status": "todo",
            "owner_ref": "7", "evidence": ""}
    base.update(over)
    return SimpleNamespace(**base)


def test_the_work_turn_carries_the_item_into_the_prompt() -> None:
    captured: dict = {}
    asyncio.run(GroupEngine.speak_work(
        _engine(_chat(captured)), _WS(), room=_room(), character=_mira(),
        history=[], item=_item(), should_stop=lambda: False,
    ))
    assert "parse the config" in captured["user_input"]


def test_the_work_turn_tells_the_member_how_to_report() -> None:
    captured: dict = {}
    asyncio.run(GroupEngine.speak_work(
        _engine(_chat(captured)), _WS(), room=_room(), character=_mira(),
        history=[], item=_item(), should_stop=lambda: False,
    ))
    assert "plan_write" in captured["user_input"]
    assert "blocked" in captured["user_input"]


def test_the_work_turn_uses_the_member_staging_when_given_one() -> None:
    captured: dict = {}
    marker = object()
    asyncio.run(GroupEngine.speak_work(
        _engine(_chat(captured)), _WS(), room=_room(), character=_mira(),
        history=[], item=_item(), should_stop=lambda: False,
        workspace_override=marker,
    ))
    assert captured["workspace_override"] is marker


def test_the_work_turn_keeps_the_rooms_fixed_tier_and_cancel() -> None:
    captured: dict = {}
    asyncio.run(GroupEngine.speak_work(
        _engine(_chat(captured)), _WS(), room=_room(), character=_mira(),
        history=[], item=_item(), should_stop=lambda: False,
    ))
    assert captured["tier_override"] == "xhigh"
    assert captured["save_character_id"] == 7
    assert captured["should_stop"]() is False


def test_the_work_turn_reports_its_own_events() -> None:
    ws = _WS()
    _mid, text = asyncio.run(GroupEngine.speak_work(
        _engine(_chat({})), ws, room=_room(), character=_mira(),
        history=[], item=_item(), should_stop=lambda: False,
    ))
    kinds = [m["type"] for m in ws.sent]
    assert kinds == ["room.work.started", "room.work.finished"]
    assert not any(k.startswith("group.speaker.") for k in kinds)
    assert text == "done"


def test_the_work_events_name_the_item_and_the_member() -> None:
    ws = _WS()
    asyncio.run(GroupEngine.speak_work(
        _engine(_chat({})), ws, room=_room(), character=_mira(),
        history=[], item=_item(), should_stop=lambda: False,
    ))
    started = ws.sent[0]
    assert started["item_key"] == "a"
    assert started["character_id"] == 7
    assert started["room_id"] == 1
    assert "message_id" in started


def test_a_failed_work_turn_reports_failure_and_no_text() -> None:
    ws = _WS()
    _mid, text = asyncio.run(GroupEngine.speak_work(
        _engine(_chat({}, conclusion="(Cancelled.)", outcome="failure")), ws,
        room=_room(), character=_mira(), history=[], item=_item(),
        should_stop=lambda: False,
    ))
    assert text == ""
    done = next(m for m in ws.sent if m["type"] == "room.work.finished")
    assert done["failed"] is True
    assert done["content"] == ""


def test_a_work_turn_with_nothing_to_say_is_still_a_failure() -> None:
    """Same rule the streaming turn follows: an empty reply is not a report."""
    ws = _WS()
    _mid, text = asyncio.run(GroupEngine.speak_work(
        _engine(_chat({}, conclusion="   ", outcome="success")), ws,
        room=_room(), character=_mira(), history=[], item=_item(),
        should_stop=lambda: False,
    ))
    assert text == ""
    assert next(m for m in ws.sent if m["type"] == "room.work.finished")["failed"] is True


def test_the_evidence_on_the_item_reaches_the_prompt() -> None:
    captured: dict = {}
    asyncio.run(GroupEngine.speak_work(
        _engine(_chat(captured)), _WS(), room=_room(), character=_mira(),
        history=[], item=_item(evidence="attempt one timed out"),
        should_stop=lambda: False,
    ))
    assert "attempt one timed out" in captured["user_input"]


def test_speak_agent_still_reports_its_own_events() -> None:
    """The extraction must not have moved the electing turn's behaviour."""
    ws = _WS()
    _mid, text = asyncio.run(GroupEngine.speak_agent(
        _engine(_chat({})), ws, room=_room(), character=_mira(), user_card=None,
        history=[], user_input="hi", should_stop=lambda: False,
    ))
    kinds = [m["type"] for m in ws.sent]
    assert kinds == ["group.speaker.start", "group.speaker.done"]
    assert text == "done"


def test_speak_agent_does_not_hand_the_loop_a_workspace() -> None:
    """Only work turns carry a staging; the electing turn keeps the room's own
    binding, which is what it resolved before."""
    captured: dict = {}
    asyncio.run(GroupEngine.speak_agent(
        _engine(_chat(captured)), _WS(), room=_room(), character=_mira(),
        user_card=None, history=[], user_input="hi", should_stop=lambda: False,
    ))
    assert captured["workspace_override"] is None

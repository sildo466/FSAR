# SPDX-License-Identifier: MIT
"""A character's turn through the agent route.

agent_mode=1 means the characters can act, not only talk. The turn is the
engine's own agent loop, driven with the room's scope: the room's cancel, the
room's fixed tier, the room's history.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from src.core.agent_runtime import AgentLoopResult
from src.memory.cards import CharacterCard
from src.server import group_engine as ge
from src.server.group_engine import GroupEngine


class _WS:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)


def _mira() -> CharacterCard:
    return CharacterCard(
        id=7, name="Mira", description="witch", personality="calm",
    )


def _room(**overrides) -> SimpleNamespace:
    base = {
        "id": 1, "session_id": "s1", "scenario_prompt": "", "name": "R",
        "user_card_id": None, "max_rounds": 0, "agent_mode": True,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _chat() -> SimpleNamespace:
    chat = SimpleNamespace()
    chat.session_store = SimpleNamespace(
        get_session_messages=lambda cid, **kw: [],
    )
    chat.card_repo = SimpleNamespace(
        get_character=lambda cid: _mira(),
        get_user_card=lambda cid: None,
        get_default_user_card=lambda: None,
    )
    chat._msg_ids = {}
    chat._short_cache = {}
    chat.client_and_model = lambda: (object(), "model", "provider")
    return chat


def _engine(chat) -> GroupEngine:
    rooms = SimpleNamespace(members=lambda room_id: [7])
    return GroupEngine(chat, rooms)


def _stub_run_agent(chat, captured: dict, *, conclusion="done",
                    outcome="success") -> None:
    """Stand in for the engine's loop on the chat object itself.

    The room talks to whatever object it was given, so the stub goes there
    rather than on ChatEngine — a real ChatEngine cannot be built here without
    an LLM provider, and none of the room's behaviour is about the loop.
    """

    async def fake(ws, message_id, client, model, conv_id, user_input,
                   character=None, char_name=None, provider_id="", **kw):
        captured.update(kw)
        captured["message_id"] = message_id
        captured["conv_id"] = conv_id
        captured["user_input"] = user_input
        captured["char_name"] = char_name
        return AgentLoopResult(conclusion, outcome)

    chat._run_agent = fake


def test_the_room_turn_uses_the_rooms_scope() -> None:
    chat = _chat()
    captured: dict = {}
    _stub_run_agent(chat, captured)
    history = [{"role": "user", "content": "[user]: ship it"}]

    _msg_id, text = asyncio.run(GroupEngine.speak_agent(
        _engine(chat), _WS(), room=_room(),
        character=_mira(), user_card=None,
        history=history, user_input="ship it", should_stop=lambda: False,
    ))

    assert captured["tier_override"] == ge.GROUP_AGENT_TIER == "xhigh"
    assert captured["save_character_id"] == 7
    assert captured["history"] == history
    assert captured["conv_id"] == "s1"
    # The room's own cancel predicate reaches the loop, not the engine's flag.
    assert captured["should_stop"]() is False
    assert text == "done"


def test_the_room_turn_reports_start_and_done() -> None:
    chat = _chat()
    _stub_run_agent(chat, {})
    ws = _WS()

    asyncio.run(GroupEngine.speak_agent(
        _engine(chat), ws, room=_room(),
        character=_mira(), user_card=None,
        history=[], user_input="hi", should_stop=lambda: False,
    ))

    kinds = [m["type"] for m in ws.sent]
    assert "group.speaker.start" in kinds
    assert "group.speaker.done" in kinds
    done = next(m for m in ws.sent if m["type"] == "group.speaker.done")
    assert done["failed"] is False
    assert done["content"] == "done"


def test_a_failed_turn_does_not_leave_a_blank_bubble() -> None:
    """The rule the streaming turn already follows: nothing to say is not a
    message."""
    chat = _chat()
    _stub_run_agent(chat, {}, conclusion="(Cancelled.)", outcome="failure")
    ws = _WS()

    _msg_id, text = asyncio.run(GroupEngine.speak_agent(
        _engine(chat), ws, room=_room(),
        character=_mira(), user_card=None,
        history=[], user_input="hi", should_stop=lambda: False,
    ))

    assert text == ""
    done = next(m for m in ws.sent if m["type"] == "group.speaker.done")
    assert done["failed"] is True


def test_the_trigger_is_wrapped_with_who_said_it() -> None:
    """The trigger must not read as the user's own words — a member is not the
    user."""
    chat = _chat()
    captured: dict = {}
    _stub_run_agent(chat, captured)

    asyncio.run(GroupEngine.speak_agent(
        _engine(chat), _WS(), room=_room(),
        character=_mira(), user_card=None,
        history=[], user_input="deploy it", should_stop=lambda: False,
        trigger_speaker="Claude",
    ))

    assert "Claude has just spoken" in captured["user_input"]
    assert "deploy it" in captured["user_input"]


def test_a_bare_trigger_is_left_as_it_came() -> None:
    """With no speaker named there is nothing to wrap it in, which is how the
    user's own opening line is delivered."""
    chat = _chat()
    captured: dict = {}
    _stub_run_agent(chat, captured)

    asyncio.run(GroupEngine.speak_agent(
        _engine(chat), _WS(), room=_room(),
        character=_mira(), user_card=None,
        history=[], user_input="kick off", should_stop=lambda: False,
    ))

    assert captured["user_input"] == "kick off"

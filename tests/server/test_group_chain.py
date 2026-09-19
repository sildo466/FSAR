# SPDX-License-Identifier: MIT
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from src.memory.cards import CharacterCard
from src.memory.session_store import MessageRow
from src.server import group_engine as ge
from src.server.group_engine import GroupEngine


class FakeWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send_json(self, message: dict) -> None:
        self.messages.append(message)


def _members() -> list[CharacterCard]:
    return [
        CharacterCard(id=7, name="Mira", description="witch", personality="calm"),
        CharacterCard(id=8, name="Kai", description="sailor", personality="loud"),
    ]


def _room(max_rounds: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        id=1, session_id="s1", scenario_prompt="", name="R", user_card_id=None,
        max_rounds=max_rounds,
    )


def _chat(members: list[CharacterCard]) -> SimpleNamespace:
    chat = SimpleNamespace()
    rows: list[MessageRow] = []
    chat.session_store = SimpleNamespace(
        get_session_messages=lambda cid, **kw: list(rows),
    )
    chat.card_repo = SimpleNamespace(
        get_character=lambda cid: next((c for c in members if c.id == cid), None),
        get_user_card=lambda cid: None,
        get_default_user_card=lambda: None,
    )
    chat._rows = rows
    return chat


def _engine(chat, members: list[CharacterCard]) -> GroupEngine:
    rooms = SimpleNamespace(members=lambda room_id: [c.id for c in members])
    return GroupEngine(chat, rooms)


def _patch(monkeypatch, *, eager: int, spoken: list[str]):
    async def fake_elect(self, ws, **kwargs):
        return [
            ge.ElectResult(
                character_id=getattr(c, "id", None),
                character_name=getattr(c, "name", ""),
                eagerness=eager,
                reason="r",
            )
            for c in kwargs["candidates"]
        ]

    monkeypatch.setattr(GroupEngine, "elect", fake_elect)

    async def fake_speak(self, ws, **kwargs):
        speaker = getattr(kwargs["character"], "name", "")
        spoken.append(speaker)
        return f"group_{len(spoken)}", "line"

    monkeypatch.setattr(GroupEngine, "speak", fake_speak)


def _run(engine, ws=None, *, max_rounds: int = 0, **kw):
    return asyncio.run(GroupEngine.run_chain(
        engine, ws or FakeWebSocket(), room=_room(max_rounds),
        user_input="hi",
        mentioned=kw.pop("mentioned", []), user_card=None, **kw,
    ))


def test_chain_settles_when_nobody_is_eager(monkeypatch) -> None:
    members = _members()
    chat = _chat(members)
    spoken: list[str] = []
    _patch(monkeypatch, eager=ge.EAGER_THRESHOLD - 1, spoken=spoken)

    reason = _run(_engine(chat, members))

    assert reason == "settled"
    assert spoken == []


def test_chain_reports_finished_when_a_round_blows_up(monkeypatch) -> None:
    """Without a terminal event the client's composer stays on Stop with
    nothing left to interrupt, bricking the room until a reload."""
    members = _members()
    chat = _chat(members)
    engine = _engine(chat, members)

    async def exploding_elect(self, ws, **kwargs):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(GroupEngine, "elect", exploding_elect)
    ws = FakeWebSocket()

    reason = _run(engine, ws)

    assert reason == "error"
    finished = next(m for m in ws.messages if m["type"] == "group.chain.finished")
    assert finished["reason"] == "error"


def test_chain_speaks_when_eagerness_meets_threshold(monkeypatch) -> None:
    members = _members()
    chat = _chat(members)
    spoken: list[str] = []
    _patch(monkeypatch, eager=ge.EAGER_THRESHOLD, spoken=spoken)

    reason = _run(_engine(chat, members), max_rounds=1)

    assert reason == "max_rounds"
    assert spoken[0] == "Mira"


def test_chain_stops_at_the_configured_round_limit(monkeypatch) -> None:
    members = _members()
    chat = _chat(members)
    spoken: list[str] = []
    _patch(monkeypatch, eager=10, spoken=spoken)

    reason = _run(_engine(chat, members), max_rounds=4)

    assert reason == "max_rounds"
    # Round 1 picks both (no previous speaker yet), then the anti-monologue
    # rule limits every later round to the single other member.
    assert len(spoken) == ge.SPEAKERS_PER_ROUND + 3


def test_uncapped_chain_runs_past_four_rounds_until_it_settles(monkeypatch) -> None:
    """No cap means the group decides when to stop; the old 4-round ceiling is
    gone, so an open-ended debate is possible."""
    members = _members()
    chat = _chat(members)
    spoken: list[str] = []
    rounds = {"n": 0}

    async def elect(self, ws, **kwargs):
        rounds["n"] += 1
        eager = 10 if rounds["n"] <= 6 else 0
        return [
            ge.ElectResult(character_id=c.id, character_name=c.name,
                           eagerness=eager, reason="r")
            for c in kwargs["candidates"]
        ]

    monkeypatch.setattr(GroupEngine, "elect", elect)

    async def fake_speak(self, ws, **kwargs):
        spoken.append(getattr(kwargs["character"], "name", ""))
        return f"group_{len(spoken)}", "line"

    monkeypatch.setattr(GroupEngine, "speak", fake_speak)

    reason = _run(_engine(chat, members))

    assert reason == "settled"
    assert rounds["n"] == 7
    assert len(spoken) == ge.SPEAKERS_PER_ROUND + 5


def test_cancel_between_rounds_is_caught_before_the_next_election(
    monkeypatch,
) -> None:
    """On an uncapped chain the per-round check is what keeps Stop responsive:
    without it the loop would start another election after the last speaker."""
    members = _members()
    chat = _chat(members)
    spoken: list[str] = []
    elections = {"n": 0}

    async def elect(self, ws, **kwargs):
        elections["n"] += 1
        return [
            ge.ElectResult(character_id=c.id, character_name=c.name,
                           eagerness=10, reason="r")
            for c in kwargs["candidates"]
        ]

    monkeypatch.setattr(GroupEngine, "elect", elect)

    async def speak_then_cancel_on_the_last(self, ws, **kwargs):
        spoken.append(getattr(kwargs["character"], "name", ""))
        if len(spoken) == 2:  # the last speaker of round one
            GroupEngine.cancel(self, kwargs["room"].id)
        return f"group_{len(spoken)}", "line"

    monkeypatch.setattr(GroupEngine, "speak", speak_then_cancel_on_the_last)

    reason = _run(_engine(chat, members))

    assert reason == "cancelled"
    assert elections["n"] == 1, "round two must not start after a cancel"
    assert len(spoken) == ge.SPEAKERS_PER_ROUND


def test_same_character_cannot_speak_twice_in_a_row(monkeypatch) -> None:
    members = [_members()[0]]
    chat = _chat(members)
    spoken: list[str] = []
    _patch(monkeypatch, eager=10, spoken=spoken)

    reason = _run(_engine(chat, members))

    assert reason == "settled"
    assert spoken == ["Mira"]


def test_cancel_stops_after_the_in_flight_speaker(monkeypatch) -> None:
    members = _members()
    chat = _chat(members)
    spoken: list[str] = []
    _patch(monkeypatch, eager=10, spoken=spoken)

    async def cancelling_speak(self, ws, **kwargs):
        spoken.append(getattr(kwargs["character"], "name", ""))
        GroupEngine.cancel(self, kwargs["room"].id)
        return f"group_{len(spoken)}", "line"

    monkeypatch.setattr(GroupEngine, "speak", cancelling_speak)

    reason = _run(_engine(chat, members))

    assert reason == "cancelled"
    assert len(spoken) == 1


def test_new_chain_clears_a_stale_cancel(monkeypatch) -> None:
    """A room cancelled mid-chain must still accept the user's next message."""
    members = _members()
    chat = _chat(members)
    spoken: list[str] = []
    _patch(monkeypatch, eager=10, spoken=spoken)
    engine = _engine(chat, members)
    GroupEngine.cancel(engine, 1)

    _run(engine, max_rounds=1)

    assert spoken
    assert engine.is_cancelled(1) is False


def test_chain_emits_decided_and_finished_events(monkeypatch) -> None:
    members = _members()
    chat = _chat(members)
    _patch(monkeypatch, eager=0, spoken=[])
    ws = FakeWebSocket()

    _run(_engine(chat, members), ws)

    finished = next(m for m in ws.messages if m["type"] == "group.chain.finished")
    assert finished["reason"] == "settled"
    assert finished["room_id"] == 1


def test_chain_decided_event_lists_speakers(monkeypatch) -> None:
    members = _members()
    chat = _chat(members)
    _patch(monkeypatch, eager=10, spoken=[])
    ws = FakeWebSocket()

    _run(_engine(chat, members), ws, max_rounds=1)

    decided = next(m for m in ws.messages if m["type"] == "group.elect.decided")
    assert decided["speakers"] == [7, 8]
    assert decided["round"] == 1


def test_chain_without_members_reports_error(monkeypatch) -> None:
    chat = _chat([])
    ws = FakeWebSocket()
    engine = _engine(chat, [])

    reason = asyncio.run(GroupEngine.run_chain(
        engine, ws, room=_room(), user_input="hi", mentioned=[], user_card=None,
    ))

    assert reason == "settled"
    error = next(m for m in ws.messages if m["type"] == "group.error")
    assert error["code"] == "no_members"


def test_mentions_only_apply_to_the_first_round(monkeypatch) -> None:
    members = _members()
    chat = _chat(members)
    rounds: list[list[int]] = []

    async def fake_elect(self, ws, **kwargs):
        rounds.append(list(kwargs["mentioned"]))
        return [
            ge.ElectResult(
                character_id=getattr(c, "id", None),
                character_name=getattr(c, "name", ""),
                eagerness=10,
                reason="r",
            )
            for c in kwargs["candidates"]
        ]

    monkeypatch.setattr(GroupEngine, "elect", fake_elect)

    async def fake_speak(self, ws, **kwargs):
        return "group_x", "line"

    monkeypatch.setattr(GroupEngine, "speak", fake_speak)

    _run(_engine(chat, members), max_rounds=2, mentioned=[7])

    assert rounds[0] == [7]
    assert all(r == [] for r in rounds[1:])


def test_history_excludes_the_trigger_message(monkeypatch) -> None:
    members = _members()
    chat = _chat(members)
    chat._rows.extend([
        MessageRow(id=1, session_id="s1", role="user", content="look"),
        MessageRow(id=2, session_id="s1", role="assistant", content="prior",
                   character_card_id=8),
        MessageRow(id=3, session_id="s1", role="user", content="hi"),
    ])
    captured: list[dict] = []

    async def fake_elect(self, ws, **kwargs):
        return [
            ge.ElectResult(character_id=c.id, character_name=c.name,
                           eagerness=10, reason="r")
            for c in kwargs["candidates"]
        ]

    monkeypatch.setattr(GroupEngine, "elect", fake_elect)

    async def fake_speak(self, ws, **kwargs):
        captured.append({
            "history": kwargs["history"],
            "user_input": kwargs["user_input"],
            "trigger_speaker": kwargs["trigger_speaker"],
        })
        chat._rows.append(MessageRow(id=10 + len(captured), session_id="s1",
                                     role="assistant", content="fresh",
                                     character_card_id=7))
        return f"group_{len(captured)}", "fresh"

    monkeypatch.setattr(GroupEngine, "speak", fake_speak)

    _run(_engine(chat, members), max_rounds=1)

    first = captured[0]
    # The user's own message is the trigger, so it stays out of the history.
    assert [m["content"] for m in first["history"]] == [
        "[user]: look", "[Kai]: prior",
    ]
    assert first["user_input"] == "hi"
    assert first["trigger_speaker"] == ""
    # Later speakers are triggered by whoever just spoke, read back from the
    # room: raw text plus the speaker, never another transcript line.
    assert captured[1]["user_input"] == "fresh"
    assert captured[1]["trigger_speaker"] == "Mira"
    assert [m["content"] for m in captured[1]["history"]] == [
        "[user]: look", "[Kai]: prior", "[user]: hi",
    ]

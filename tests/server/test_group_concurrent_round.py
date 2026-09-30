# SPDX-License-Identifier: MIT
"""A round in an agent room runs its speakers at the same time; a round in a
companion room runs them one after another.

Concurrency is gated on agent_mode on purpose: the anti-monologue rule that
alternates speakers is what a companion room's rhythm is built on, and replacing
it with a set per round would silence a two-character room after one round.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from src.memory.cards import CharacterCard
from src.memory.session_store import MessageRow
from src.server import group_engine as ge
from src.server.group_engine import GroupEngine


class _WS:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)


def _characters() -> list[CharacterCard]:
    return [
        CharacterCard(id=7, name="Mira", description="witch", personality="calm"),
        CharacterCard(id=8, name="Kai", description="sailor", personality="loud"),
    ]


def _chat(rows: list[MessageRow]) -> SimpleNamespace:
    chat = SimpleNamespace()
    chat.session_store = SimpleNamespace(
        get_session_messages=lambda cid, **kw: list(rows),
    )
    chat.card_repo = SimpleNamespace(
        get_character=lambda cid: next(
            (c for c in _characters() if c.id == cid), None
        ),
        get_user_card=lambda cid: None,
        get_default_user_card=lambda: None,
    )
    chat._short_cache = {}
    chat._msg_ids = {}
    return chat


def _engine(chat, members) -> GroupEngine:
    rooms = SimpleNamespace(members=lambda room_id: [c.id for c in members])
    return GroupEngine(chat, rooms)


def _room(agent_mode: bool) -> SimpleNamespace:
    return SimpleNamespace(
        id=1, session_id="s1", scenario_prompt="", name="R", user_card_id=None,
        max_rounds=1, agent_mode=agent_mode,
    )


def _all_eager(monkeypatch) -> None:
    async def elect(self, ws, **kwargs):
        return [
            ge.ElectResult(character_id=c.id, character_name=c.name,
                           eagerness=10, reason="r")
            for c in kwargs["candidates"]
        ]

    monkeypatch.setattr(GroupEngine, "elect", elect)


def _stub_both_routes(monkeypatch, log: list[str], *, pause: bool) -> None:
    """Both routes are stubbed so neither can be the one that ran by accident.

    A missing route shows up as the other route's name in `log` rather than as
    an exception from deep inside a real turn.
    """

    async def speak(self, ws, *, character, **kwargs):
        log.append(f"companion:{character.name}")
        if pause:
            await asyncio.sleep(0.01)
        return "m", "line"

    async def speak_agent(self, ws, *, character, **kwargs):
        log.append(f"agent:{character.name}")
        if pause:
            await asyncio.sleep(0.01)
        return "m", "line"

    monkeypatch.setattr(GroupEngine, "speak", speak)
    monkeypatch.setattr(GroupEngine, "speak_agent", speak_agent)


def _run(chat, members, *, agent_mode: bool, user_input: str = "go"):
    return asyncio.run(GroupEngine.run_chain(
        _engine(chat, members), _WS(), room=_room(agent_mode),
        user_input=user_input, mentioned=[], user_card=None,
    ))


def test_an_agent_room_uses_the_agent_route(monkeypatch) -> None:
    log: list[str] = []
    _stub_both_routes(monkeypatch, log, pause=False)
    _all_eager(monkeypatch)

    _run(_chat([]), _characters(), agent_mode=True)

    assert sorted(log) == ["agent:Kai", "agent:Mira"]


def test_a_companion_room_uses_the_companion_route(monkeypatch) -> None:
    """The switch has to be the thing that decides. A companion room that
    quietly ran the agent route would be a behaviour change to rooms that have
    already shipped."""
    log: list[str] = []
    _stub_both_routes(monkeypatch, log, pause=False)
    _all_eager(monkeypatch)

    _run(_chat([]), _characters(), agent_mode=False)

    assert sorted(log) == ["companion:Kai", "companion:Mira"]


def test_an_agent_room_starts_the_rounds_speakers_together(monkeypatch) -> None:
    """Both turns are in flight before either finishes. A round that awaited
    one speaker before starting the next would be sequential with extra steps."""
    order: list[str] = []

    async def speak_agent(self, ws, *, character, **kwargs):
        order.append(f"start:{character.name}")
        await asyncio.sleep(0.01)
        order.append(f"end:{character.name}")
        return "m", "line"

    monkeypatch.setattr(GroupEngine, "speak_agent", speak_agent)
    _all_eager(monkeypatch)

    _run(_chat([]), _characters(), agent_mode=True)

    assert sorted(order[:2]) == ["start:Kai", "start:Mira"]
    assert sorted(order[2:]) == ["end:Kai", "end:Mira"]


def test_a_companion_room_takes_its_turns_one_at_a_time(monkeypatch) -> None:
    order: list[str] = []

    async def speak(self, ws, *, character, **kwargs):
        order.append(f"start:{character.name}")
        await asyncio.sleep(0.01)
        order.append(f"end:{character.name}")
        return "m", "line"

    monkeypatch.setattr(GroupEngine, "speak", speak)
    _all_eager(monkeypatch)

    _run(_chat([]), _characters(), agent_mode=False)

    # Strictly interleaved: each turn finishes before the next one starts.
    assert order[0].startswith("start:") and order[1] == order[0].replace(
        "start:", "end:"
    )
    assert order[2].startswith("start:") and order[3] == order[2].replace(
        "start:", "end:"
    )


def test_every_speaker_in_a_concurrent_round_gets_the_same_history(
    monkeypatch,
) -> None:
    """The triggers are computed from one snapshot. Computed as each turn
    starts, the second speaker's trigger would be whatever the first had
    already written — a race with a nondeterministic answer."""
    rows = [
        MessageRow(id=1, session_id="s1", role="assistant", content="earlier",
                   character_card_id=7),
        MessageRow(id=2, session_id="s1", role="user", content="kick off"),
    ]
    seen: list[tuple] = []

    async def speak_agent(self, ws, *, character, history, user_input, **kwargs):
        seen.append((
            character.name, tuple(m["content"] for m in history), user_input,
        ))
        return "m", "line"

    monkeypatch.setattr(GroupEngine, "speak_agent", speak_agent)
    _all_eager(monkeypatch)

    _run(_chat(rows), _characters(), agent_mode=True, user_input="kick off")

    assert len(seen) == 2, "both speakers of the round reached the agent route"
    # The round's lines, minus the trigger, which is delivered as an
    # instruction instead of as another transcript entry.
    assert [row[1] for row in seen] == [("[Mira]: earlier",)] * 2
    assert [row[2] for row in seen] == ["kick off"] * 2

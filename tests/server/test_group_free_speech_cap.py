# SPDX-License-Identifier: MIT
"""Only rooms that have agent members get a chain cap."""

from __future__ import annotations

from types import SimpleNamespace

from src.server.handlers import group as group_handler


def _wire(*, agent_refs: list[str], max_rounds: int):
    agents = SimpleNamespace(
        members=lambda room_id: [
            SimpleNamespace(ref=r, display_name=r, state="active")
            for r in agent_refs
        ],
    )
    group_handler.set_engine(
        SimpleNamespace(chat=SimpleNamespace(session_store=SimpleNamespace())),
        SimpleNamespace(),
        agents,
    )
    return SimpleNamespace(id=1, max_rounds=max_rounds)


def test_free_speech_room_gets_a_cap() -> None:
    room = _wire(agent_refs=["claude-laptop"], max_rounds=0)
    assert group_handler._chain_cap_for(room) == group_handler.FREE_SPEECH_MAX_ROUNDS


def test_companion_room_keeps_unlimited() -> None:
    room = _wire(agent_refs=[], max_rounds=0)
    assert group_handler._chain_cap_for(room) is None


def test_explicit_room_cap_wins_over_the_default() -> None:
    room = _wire(agent_refs=["claude-laptop"], max_rounds=9)
    assert group_handler._chain_cap_for(room) is None


def test_cap_is_none_when_the_agent_store_is_not_wired(monkeypatch) -> None:
    monkeypatch.setattr(group_handler, "_agent_members", None)
    room = SimpleNamespace(id=1, max_rounds=0)
    assert group_handler._chain_cap_for(room) is None

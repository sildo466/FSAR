# SPDX-License-Identifier: MIT
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from src.memory.cards import CharacterCard
from src.server import group_engine as ge
from src.server.group_engine import GroupEngine


class FakeWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send_json(self, message: dict) -> None:
        self.messages.append(message)


def _chat() -> SimpleNamespace:
    chat = SimpleNamespace()
    chat.client_and_model = lambda: (SimpleNamespace(base_url=""), "m", "p")
    return chat


def _card(char_id: int, name: str) -> CharacterCard:
    return CharacterCard(
        id=char_id, name=name,
        description="d", personality="p",
    )


def _patch_batch(monkeypatch, replies: dict[str, str], calls: list[dict]) -> None:
    async def fake_batch(client, *, provider_id, model, prompts):
        out = []
        for prompt in prompts:
            calls.append({"prompt": prompt})
            name = next(
                (n for n in replies if f"Your name is {n}." in prompt), None,
            )
            out.append(replies.get(name, ""))
        return out

    monkeypatch.setattr(ge, "run_batch_completions", fake_batch)


def _elect(engine, ws, candidates, mentioned=None, scenario="", round_no=1):
    return asyncio.run(GroupEngine.elect(
        engine, ws,
        room=SimpleNamespace(id=1, scenario_prompt=scenario),
        candidates=candidates,
        history_block=[],
        mentioned=mentioned or [],
        chain_id="c1",
        round_no=round_no,
    ))


def test_elect_orders_by_eagerness(monkeypatch) -> None:
    calls: list[dict] = []
    _patch_batch(monkeypatch, {
        "Mira": '{"eagerness": 3, "reason": "meh"}',
        "Kai": '{"eagerness": 9, "reason": "I must speak"}',
    }, calls)
    engine = GroupEngine(_chat(), SimpleNamespace())

    results = _elect(engine, FakeWebSocket(), [_card(7, "Mira"), _card(8, "Kai")])

    assert [r.character_id for r in results] == [8, 7]
    assert results[0].eagerness == 9
    assert results[0].reason == "I must speak"
    assert results[0].character_name == "Kai"


def test_elect_emits_started_and_candidate_events(monkeypatch) -> None:
    _patch_batch(monkeypatch, {"Mira": '{"eagerness": 6, "reason": "curious"}'}, [])
    engine = GroupEngine(_chat(), SimpleNamespace())
    ws = FakeWebSocket()

    _elect(engine, ws, [_card(7, "Mira")])

    kinds = [m["type"] for m in ws.messages]
    assert kinds == ["group.elect.started", "group.elect.candidate"]
    started = ws.messages[0]
    assert started["candidates"] == [7]
    assert started["round"] == 1
    candidate = ws.messages[1]
    assert candidate["eagerness"] == 6
    assert candidate["reason"] == "curious"
    assert candidate["character_name"] == "Mira"


def test_mentioned_character_short_circuits_to_front(monkeypatch) -> None:
    _patch_batch(monkeypatch, {
        "Mira": '{"eagerness": 2, "reason": "quiet"}',
        "Kai": '{"eagerness": 10, "reason": "loud"}',
    }, [])
    engine = GroupEngine(_chat(), SimpleNamespace())

    results = _elect(
        engine, FakeWebSocket(), [_card(7, "Mira"), _card(8, "Kai")],
        mentioned=[7],
    )

    assert results[0].character_id == 7
    assert results[0].eagerness == ge.MENTIONED_EAGERNESS
    assert results[0].reason == "mentioned"
    assert results[1].character_id == 8


def test_election_prompt_is_lightweight(monkeypatch) -> None:
    """Election runs once per member per round, so it must not carry the full
    persona, examples or long-term memory."""
    calls: list[dict] = []
    _patch_batch(monkeypatch, {"Mira": '{"eagerness": 5, "reason": "x"}'}, calls)
    engine = GroupEngine(_chat(), SimpleNamespace())

    _elect(engine, FakeWebSocket(), [_card(7, "Mira")], scenario="stranded island")

    prompt = calls[0]["prompt"]
    assert "Your name is Mira." in prompt
    assert "stranded island" in prompt
    assert "[CHARACTER CARD]" not in prompt
    assert "[CLEANSED MEMORY]" not in prompt


def test_election_prompt_includes_history(monkeypatch) -> None:
    calls: list[dict] = []
    _patch_batch(monkeypatch, {"Mira": '{"eagerness": 5, "reason": "x"}'}, calls)
    engine = GroupEngine(_chat(), SimpleNamespace())
    ws = FakeWebSocket()

    asyncio.run(GroupEngine.elect(
        engine, ws,
        room=SimpleNamespace(id=1, scenario_prompt=""),
        candidates=[_card(7, "Mira")],
        history_block=[
            {"role": "user", "content": "[tester]: look"},
            {"role": "assistant", "content": "[Kai]: watch out"},
        ],
        mentioned=[],
        chain_id="c1",
        round_no=2,
    ))

    assert "[Kai]: watch out" in calls[0]["prompt"]


def test_empty_candidates_short_circuits(monkeypatch) -> None:
    async def explode(*args, **kwargs):
        raise AssertionError("should not call the model")

    monkeypatch.setattr(ge, "run_batch_completions", explode)
    engine = GroupEngine(_chat(), SimpleNamespace())
    ws = FakeWebSocket()

    assert _elect(engine, ws, []) == []
    assert ws.messages == []


def test_failed_call_does_not_block_others(monkeypatch) -> None:
    async def fake_batch(client, *, provider_id, model, prompts):
        return ["", '{"eagerness": 7, "reason": "still here"}']

    monkeypatch.setattr(ge, "run_batch_completions", fake_batch)
    engine = GroupEngine(_chat(), SimpleNamespace())

    results = _elect(engine, FakeWebSocket(), [_card(7, "Mira"), _card(8, "Kai")])

    assert [r.eagerness for r in results] == [7, 0]

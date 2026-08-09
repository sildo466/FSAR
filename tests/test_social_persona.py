import pytest

import src.server.chat_engine as ce
import src.server.ws_server as ws_mod

from types import SimpleNamespace


class _Stop(Exception):
    """Halts the agent loop right after the system prompt is assembled."""


@pytest.fixture
def unbound_engine(monkeypatch):
    """An engine whose card set has no default and no session binding.

    This is the state a fresh WeChat peer lands in: the social router creates
    its own session, so nothing points at a character card.
    """
    engine = ws_mod._engine
    card = engine.card_repo.list_characters()[0]
    monkeypatch.setattr(engine.card_repo, "get_default_character", lambda: None)
    monkeypatch.setattr(engine.session_store, "get_character", lambda conv_id: None)
    return engine, card


def test_build_prompt_accepts_a_resolved_character(unbound_engine):
    engine, card = unbound_engine

    prompt = engine._build_prompt("conv-1", "agent", "hello", character=card)

    assert card.name in prompt


def test_build_prompt_still_resolves_when_no_character_passed(unbound_engine, monkeypatch):
    engine, card = unbound_engine
    monkeypatch.setattr(engine.card_repo, "get_default_character", lambda: card)

    prompt = engine._build_prompt("conv-1", "agent", "hello")

    assert card.name in prompt


async def test_subagent_prompt_keeps_the_resolved_character(unbound_engine, monkeypatch):
    """Sub-agents rebuild the system prompt from the shared runtime, so the
    resolved card has to travel with it or they hit the same missing persona."""
    from src.core.agent_runtime import AgentLoopResult, AgentRecord, AgentRunState
    from src.core.agent_tiers import get_tier_profile

    engine, card = unbound_engine
    captured: dict = {}

    async def fake_loop(**kwargs):
        captured["prompt"] = kwargs["base_system_prompt"]
        return AgentLoopResult(conclusion="done", outcome="success")

    monkeypatch.setattr(engine, "_agent_loop", fake_loop)
    runtime = AgentRunState(root_task_id="root", profile=get_tier_profile("medium"))
    runtime.character = card
    record = AgentRecord(
        agent_id="sub-1", parent_id="root", depth=1,
        label="Sub", assignment="do a thing",
    )

    await engine._run_subagent(
        ws=ce._NoOpWebSocket(), message_id="m1", client=object(),
        model="model-x", provider_id="prov", conv_id="social-conv",
        runtime=runtime, record=record,
    )

    assert card.name in captured["prompt"]


def test_handle_user_message_threads_the_fallback_character(monkeypatch):
    """The social bridge has no session binding, so handle_user_message falls
    back through the card list; the persona block must be built from that card
    rather than re-resolved from an empty session."""
    card = SimpleNamespace(id=7, name="Ori")

    class Config:
        chat_default_model = {"kind": "model", "provider": "p", "model": "m"}
        memory_sqlite_path = "unused.db"

        def get(self, key, default=None):
            return default

        def get_llm_config(self, provider_id):
            return {"model": "m", "max_output_tokens": 512}

    captured: dict = {}

    def spy(**kwargs):
        captured.update(kwargs)
        raise _Stop()

    monkeypatch.setattr(ce, "get_default_config", lambda: Config())
    monkeypatch.setattr(ce, "CardRepo", lambda path: SimpleNamespace(
        get_character=lambda card_id: None,
        get_default_character=lambda: None,
        list_characters=lambda: [card],
        get_user_card=lambda user_card_id: None,
        get_default_user_card=lambda: None,
    ))
    monkeypatch.setattr(ce, "SessionStore", lambda path: SimpleNamespace(
        get_character=lambda session_id: None,
    ))
    monkeypatch.setattr(ce, "build_system_prompt", spy)

    with pytest.raises(_Stop):
        ce.handle_user_message("social-conv", "hi there")

    assert captured["character"] is card

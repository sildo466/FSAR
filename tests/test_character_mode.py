"""Character-mode prompt assembly and agent prompt gating."""
from __future__ import annotations

from src.core.persona import CharacterPersona, assemble_character_persona_block
from src.core.prompts import (
    AGENT_SYSTEM_PROMPT,
    CHARACTER_MODE_PROMPT,
    SLIM_AGENT_SYSTEM_PROMPT,
    build_character_prompt,
)
from src.memory.cards import CharacterCard, UserCard


def make_character(**over: object) -> CharacterCard:
    base: dict[str, object] = {
        "id": 9,
        "name": "Mira",
        "description": "A traveling witch.",
        "personality": "Calm, sharp, mildly lazy.",
        "scenario": "In a room with the user.",
    }
    base.update(over)
    return CharacterCard(**base)  # type: ignore[arg-type]


def make_user_card() -> UserCard:
    return UserCard(
        id=2,
        name="tester",
        description="Likes direct talk.",
        preferences={},
        interests=[],
        communication_style="concise",
        is_default=0,
        created_by="user",
    )


def test_prompt_order_character_first():
    prompt = build_character_prompt(
        character=make_character(),
        user_card=make_user_card(),
        memory_block="[CLEANSED MEMORY]\n- user name is tester",
        workspace_line="Where you keep things you make: C:\\out",
    )
    assert prompt.index("[CHARACTER CARD]") < prompt.index("[USER CARD]")
    assert prompt.index("[USER CARD]") < prompt.index("You are Mira")
    assert prompt.index("You are Mira") < prompt.index("[CLEANSED MEMORY]")
    assert prompt.index("[CLEANSED MEMORY]") <= prompt.index("Where you keep things")


def test_character_prompt_has_no_fsar_engineering():
    prompt = build_character_prompt(character=make_character(), user_card=make_user_card())
    for forbidden in [
        "You are FSAR",
        "Learned Strategies",
        "## Experiences",
        "SANDBOX CONTEXT",
        "MCP server",
    ]:
        assert forbidden not in prompt


def test_character_override_after_card_before_user():
    c = make_character(
        system_prompt_override=(
            "Style: Keep Geralt's gruff tone. Direct, useful, no acting."
        )
    )
    prompt = build_character_prompt(character=c, user_card=make_user_card())
    assert prompt.index("Keep Geralt") < prompt.index("[USER CARD]")


def test_persona_block_split():
    p: CharacterPersona = assemble_character_persona_block(
        make_character(), make_user_card()
    )
    assert "[CHARACTER CARD]" in p.character_block
    assert "[USER CARD]" not in p.character_block
    assert "You are talking to tester" in p.user_block


def test_prompt_persona_share_at_least_half():
    c = make_character()
    prompt = build_character_prompt(character=c, user_card=make_user_card())
    character_content = len(CHARACTER_MODE_PROMPT)
    total = len(prompt)
    assert character_content / total >= 0.5


def test_agent_prompts_forbid_router():
    assert "[PROHIBITED] Never call a tool named `router`" in AGENT_SYSTEM_PROMPT
    assert "[PROHIBITED] Never call a tool named `router`" in SLIM_AGENT_SYSTEM_PROMPT


# ---- Task 2: router tool + registry mode gating ----

import asyncio

from src.tools import create_default_registry
from src.tools.builtin.router_tool import RouterTool


def test_router_bilingual_hit_and_miss():
    tool = RouterTool()
    hit = asyncio.run(tool.execute(keywords="读文件"))
    assert hit.startswith("__UNLOCK__:")
    assert "file_ops" in hit
    miss = asyncio.run(tool.execute(keywords="zqxjkz"))
    assert miss == "You try, but this way does not seem to open. Try different words?"
    en_hit = asyncio.run(tool.execute(keywords="search the web for news"))
    assert "web_search" in en_hit


def test_router_is_character_only():
    registry = create_default_registry()
    agent_schemas = registry.get_tools_for_llm(mode="agent")
    character_schemas = registry.get_tools_for_llm(mode="character")
    names_agent = {s["function"]["name"] for s in agent_schemas}
    names_character = {s["function"]["name"] for s in character_schemas}
    assert "router" not in names_agent
    assert "router" in names_character
    assert "file_ops" in names_agent  # real tools still available to agent


def test_router_error_message_on_exception():
    from unittest.mock import patch
    tool = RouterTool()
    with patch("src.core.router_map.match_intent", side_effect=RuntimeError("boom")):
        out = asyncio.run(tool.execute(keywords="read"))
    assert out == "You try, but nothing happens this time."


# ---- Task 3: session-persistent unlocked_tools ----

import tempfile
from pathlib import Path

from src.memory.session_store import SessionStore


def test_unlocked_tools_roundtrip():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        store = SessionStore(Path(d) / "mem.db")
        row = store.create()
        store.set_unlocked_tools(row.id, {"file_ops", "edit"})
        assert store.get_unlocked_tools(row.id) == {"file_ops", "edit"}
        store.set_unlocked_tools(row.id, set())
        assert store.get_unlocked_tools(row.id) == set()


def test_unlocked_tools_missing_column_safe():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        store = SessionStore(Path(d) / "mem.db")
        row = store.create()
        assert store.get_unlocked_tools(row.id) == set()
        store.set_unlocked_tools(row.id, {"x"})  # must not raise


# ---- Task 4: LLM memory cleanser ----

import json as _json
from types import SimpleNamespace

import src.memory.cleanse as cleanse_mod
from src.memory.cleanse import cleanse_memory_block


def _fake_completion(mapping):
    def _cc(client, *, provider_id, model, messages, max_tokens, stream, **kw):
        kept = mapping(messages)
        msg = SimpleNamespace(content=_json.dumps({"keep": kept}))
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])
    return _cc


def test_cleanse_keeps_user_items_drops_tool_strategy(monkeypatch):
    raw = (
        "[Saved Facts]\n- 我叫tester\n"
        "[User Profile]\n- language: Chinese-speaking user\n"
        "[Known Preferences]\n- task_strategy::gui: Continue using chat.llm for similar tasks\n"
    )
    char = make_character(id=9)
    fake = _fake_completion(lambda m: ["F1", "P1"])
    monkeypatch.setattr(cleanse_mod, "chat_completion", fake)
    out = cleanse_memory_block(raw, char, None, "m", "p", cache={})
    assert "我叫tester" in out
    assert "chat.llm" not in out


def test_cleanse_no_matches_returns_empty(monkeypatch):
    raw = "[User Profile]\n- technical_level: Comfortable with GitHub API"
    char = make_character(id=9)
    fake = _fake_completion(lambda m: [])
    monkeypatch.setattr(cleanse_mod, "chat_completion", fake)
    assert cleanse_memory_block(raw, char, None, "m", "p") == ""


def test_cleanse_failure_injects_nothing(monkeypatch):
    raw = "[User Profile]\n- secret config thing"
    char = make_character(id=9)

    def boom(*a, **k):
        raise RuntimeError("model call failed")

    monkeypatch.setattr(cleanse_mod, "chat_completion", boom)
    assert cleanse_memory_block(raw, char, None, "m", "p") == ""


def test_cleanse_cache_hit_skips_llm(monkeypatch):
    raw = "[User Profile]\n- language zh"
    char = make_character(id=9)
    cache = {}
    calls = {"n": 0}

    def counting(*a, **k):
        calls["n"] += 1
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"keep": ["P1"]}'))]
        )

    monkeypatch.setattr(cleanse_mod, "chat_completion", counting)
    first = cleanse_memory_block(raw, char, None, "m", "p", cache=cache)
    second = cleanse_memory_block(raw, char, None, "m", "p", cache=cache)
    assert first == second
    assert calls["n"] == 1

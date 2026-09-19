# SPDX-License-Identifier: MIT
from __future__ import annotations

from src.core.prompts import build_character_prompt
from src.memory.cards import CharacterCard, UserCard


def make_character() -> CharacterCard:
    return CharacterCard(
        id=9,
        name="Mira",
        description="A traveling witch.",
        personality="Calm, sharp, mildly lazy.",
        scenario="In a room with the user.",
    )


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


def test_tools_disabled_drops_router_instruction() -> None:
    prompt = build_character_prompt(
        character=make_character(), user_card=None, tools_enabled=False,
    )
    assert "`router`" not in prompt


def test_tools_enabled_keeps_router_instruction() -> None:
    prompt = build_character_prompt(
        character=make_character(), user_card=None, tools_enabled=True,
    )
    assert "`router`" in prompt


def test_tools_enabled_is_the_default() -> None:
    prompt = build_character_prompt(character=make_character(), user_card=None)
    assert "`router`" in prompt


def test_tools_disabled_declares_no_world_agency() -> None:
    prompt = build_character_prompt(
        character=make_character(), user_card=None, tools_enabled=False,
    )
    assert "no tools" in prompt


def test_room_scene_sits_between_persona_and_mode_prompt() -> None:
    prompt = build_character_prompt(
        character=make_character(),
        user_card=None,
        room_scene="We crashed on a deserted island and must survive.",
        tools_enabled=False,
    )
    assert "<room_scene>" in prompt
    assert "deserted island" in prompt
    assert prompt.index("[CHARACTER CARD]") < prompt.index("<room_scene>")
    assert prompt.index("<room_scene>") < prompt.index("You are Mira")


def test_room_scene_comes_after_character_scenario() -> None:
    prompt = build_character_prompt(
        character=make_character(),
        user_card=None,
        room_scene="We are on an island.",
        tools_enabled=False,
    )
    assert prompt.index("In a room with the user.") < prompt.index("We are on an island.")


def test_room_scene_precedes_user_card_block() -> None:
    prompt = build_character_prompt(
        character=make_character(),
        user_card=make_user_card(),
        room_scene="We are on an island.",
        tools_enabled=False,
    )
    assert prompt.index("<room_scene>") < prompt.index("[USER CARD]")


def test_empty_room_scene_is_not_injected() -> None:
    prompt = build_character_prompt(
        character=make_character(), user_card=None, room_scene="   ",
        tools_enabled=False,
    )
    assert "<room_scene>" not in prompt


def test_room_scene_still_before_cleansed_memory() -> None:
    prompt = build_character_prompt(
        character=make_character(),
        user_card=None,
        room_scene="We are on an island.",
        memory_block="[CLEANSED MEMORY]\n- likes tea",
        tools_enabled=False,
    )
    assert prompt.index("<room_scene>") < prompt.index("[CLEANSED MEMORY]")


def test_group_mode_forbids_self_prefixing() -> None:
    """The transcript marks speakers as "[Name]: ..." — the model must not
    copy that convention into its own reply."""
    prompt = build_character_prompt(
        character=make_character(),
        user_card=None,
        tools_enabled=False,
        group_mode=True,
    )
    assert "[Name]: ..." in prompt
    assert "no name prefix" in prompt


def test_group_mode_is_off_by_default() -> None:
    prompt = build_character_prompt(
        character=make_character(), user_card=None, tools_enabled=False,
    )
    assert "no name prefix" not in prompt


def test_group_mode_clause_sits_after_mode_prompt_and_before_memory() -> None:
    prompt = build_character_prompt(
        character=make_character(),
        user_card=None,
        memory_block="[CLEANSED MEMORY]\n- likes tea",
        tools_enabled=False,
        group_mode=True,
    )
    assert prompt.index("You are Mira") < prompt.index("no name prefix")
    assert prompt.index("no name prefix") < prompt.index("[CLEANSED MEMORY]")

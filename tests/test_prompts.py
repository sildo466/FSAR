# SPDX-License-Identifier: MIT
from __future__ import annotations

from src.core.prompts import (
    CHARACTER_ACTION_CLAUSE,
    CHARACTER_MODE_PROMPT,
    COMPANION_SYSTEM_PROMPT,
    MEMORY_POLICY,
    build_character_prompt,
    build_system_prompt,
)
from src.memory.cards import CharacterCard

BLOCK = "<time>\nIt is now Saturday 2026-09-26, 23:41.\n</time>"

# No trailing newline: build_character_prompt strips its character block while
# build_system_prompt does not, so the two goldens differ by exactly that "\n".
_CHARACTER_BLOCK = (
    "[CHARACTER CARD]\n"
    "Name: V\n"
    "Description: d\n"
    "Personality: p\n"
    "Scenario: (none)"
)


def _character() -> CharacterCard:
    return CharacterCard(id=1, name="V", description="d", personality="p")


def test_system_prompt_empty_block_is_unchanged():
    got = build_system_prompt(
        mode="companion", character=_character(), user_card=None, time_block="",
    )
    expected = "\n\n".join(
        [_CHARACTER_BLOCK + "\n", COMPANION_SYSTEM_PROMPT, MEMORY_POLICY]
    )
    assert got == expected


def test_system_prompt_appends_block_last():
    got = build_system_prompt(
        mode="companion", character=_character(), user_card=None, time_block=BLOCK,
    )
    expected = "\n\n".join(
        [_CHARACTER_BLOCK + "\n", COMPANION_SYSTEM_PROMPT, MEMORY_POLICY, BLOCK]
    )
    assert got == expected


def test_character_prompt_empty_block_is_unchanged():
    got = build_character_prompt(
        character=_character(), user_card=None, time_block="",
    )
    expected = "\n\n".join([
        _CHARACTER_BLOCK,
        CHARACTER_MODE_PROMPT.format(name="V", action_clause=CHARACTER_ACTION_CLAUSE),
        MEMORY_POLICY,
    ])
    assert got == expected


def test_character_prompt_appends_block_last():
    got = build_character_prompt(
        character=_character(), user_card=None, time_block=BLOCK,
    )
    expected = "\n\n".join([
        _CHARACTER_BLOCK,
        CHARACTER_MODE_PROMPT.format(name="V", action_clause=CHARACTER_ACTION_CLAUSE),
        MEMORY_POLICY,
        BLOCK,
    ])
    assert got == expected

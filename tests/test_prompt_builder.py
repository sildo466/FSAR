# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.prompts import (
    CHARACTER_ACTION_CLAUSE,
    CHARACTER_MODE_PROMPT,
    COMPANION_SYSTEM_PROMPT,
    MEMORY_POLICY,
    build_character_prompt,
    build_system_prompt,
)
from src.core.persona import PersonaMissingError
from src.memory.cards import CharacterCard, UserCard


def _char(**o):
    base = dict(id=1, name="FSAR", description="d", personality="p", scenario="",
                example_dialogues=[], tags=[], is_default=1, created_by="user",
                created_at="", updated_at="",
                emotion_state={"affection": 50})
    base.update(o)
    return CharacterCard(**base)


def _user(**o):
    base = dict(id=1, name="u", description="d", preferences={},
                interests=[], communication_style="")
    base.update(o)
    return UserCard(**base)


def test_build_prompt_includes_persona_and_base():
    prompt = build_system_prompt(mode="agent", character=_char(), user_card=_user())
    assert "[CHARACTER CARD]" in prompt
    assert "Name: FSAR" in prompt
    assert "[USER CARD]" in prompt
    assert "You are FSAR" in prompt
    assert "memory_policy" in prompt


def test_build_prompt_includes_emotion_state():
    prompt = build_system_prompt(mode="agent", character=_char(), user_card=None)
    assert "[EMOTION STATE]" in prompt
    assert "affection" in prompt


def test_build_prompt_appends_override_to_base():
    char = _char(system_prompt_override="EXTRA: be pirate")
    prompt = build_system_prompt(mode="agent", character=char, user_card=None)
    base_pos = prompt.find("You are FSAR")
    override_pos = prompt.find("EXTRA: be pirate")
    assert base_pos > 0 and override_pos > 0
    assert override_pos > base_pos


def test_build_prompt_skips_override_when_empty():
    prompt = build_system_prompt(mode="agent", character=_char(), user_card=None)
    assert "EXTRA" not in prompt


def test_build_prompt_companion_mode_uses_companion_base():
    prompt = build_system_prompt(mode="companion", character=_char(), user_card=None)
    assert "concise and friendly" in prompt


def test_build_prompt_raises_when_character_missing():
    with pytest.raises(PersonaMissingError):
        build_system_prompt(mode="agent", character=None, user_card=None)


# ---------- time block wiring ----------

_TIME_BLOCK = "<time>\nIt is now Saturday 2026-09-26, 23:41.\n</time>"

# No trailing newline: build_character_prompt strips its character block while
# build_system_prompt does not, so the two goldens differ by exactly that "\n".
_PLAIN_BLOCK = (
    "[CHARACTER CARD]\n"
    "Name: V\n"
    "Description: d\n"
    "Personality: p\n"
    "Scenario: (none)"
)


def _plain_char() -> CharacterCard:
    """No emotion state and no example dialogues, so the persona prefix is
    exactly _PLAIN_BLOCK and the goldens can be literals."""
    return CharacterCard(id=1, name="V", description="d", personality="p")


def test_system_prompt_empty_block_is_unchanged():
    got = build_system_prompt(
        mode="companion", character=_plain_char(), user_card=None, time_block="",
    )
    expected = "\n\n".join(
        [_PLAIN_BLOCK + "\n", COMPANION_SYSTEM_PROMPT, MEMORY_POLICY]
    )
    assert got == expected


def test_system_prompt_appends_block_last():
    got = build_system_prompt(
        mode="companion", character=_plain_char(), user_card=None,
        time_block=_TIME_BLOCK,
    )
    expected = "\n\n".join(
        [_PLAIN_BLOCK + "\n", COMPANION_SYSTEM_PROMPT, MEMORY_POLICY, _TIME_BLOCK]
    )
    assert got == expected


def test_character_prompt_empty_block_is_unchanged():
    got = build_character_prompt(
        character=_plain_char(), user_card=None, time_block="",
    )
    expected = "\n\n".join([
        _PLAIN_BLOCK,
        CHARACTER_MODE_PROMPT.format(name="V", action_clause=CHARACTER_ACTION_CLAUSE),
        MEMORY_POLICY,
    ])
    assert got == expected


def test_character_prompt_appends_block_last():
    got = build_character_prompt(
        character=_plain_char(), user_card=None, time_block=_TIME_BLOCK,
    )
    expected = "\n\n".join([
        _PLAIN_BLOCK,
        CHARACTER_MODE_PROMPT.format(name="V", action_clause=CHARACTER_ACTION_CLAUSE),
        MEMORY_POLICY,
        _TIME_BLOCK,
    ])
    assert got == expected

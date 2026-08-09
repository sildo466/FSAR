# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.persona import (
    PersonaBlock,
    PersonaMissingError,
    assemble_persona_block,
)
from src.memory.cards import CharacterCard, UserCard


def _character(**overrides) -> CharacterCard:
    base = dict(
        id=1, name="FSAR",
        description="Personal AI companion",
        personality="friendly", scenario="",
        example_dialogues=[],
        tags=[], is_default=1, created_by="builtin",
        created_at="", updated_at="",
        emotion_state={"affection": 50, "mood": 0, "energy": 50,
                       "trust": 50, "empathy": 50, "playfulness": 50, "formality": 50},
    )
    base.update(overrides)
    return CharacterCard(**base)


def _user(**overrides) -> UserCard:
    base = dict(
        id=1, name="default-user",
        description="FSAR owner",
        preferences={"language": "zh"},
        interests=[], communication_style="concise",
    )
    base.update(overrides)
    return UserCard(**base)


def test_assemble_with_full_inputs():
    block = assemble_persona_block(_character(), _user())
    assert isinstance(block, PersonaBlock)
    assert block.character_id == 1
    assert block.user_card_id == 1
    assert "[CHARACTER CARD]" in block.text
    assert "Name: FSAR" in block.text
    assert "[USER CARD]" in block.text
    assert "default-user" in block.text
    assert "[EMOTION STATE]" in block.text
    assert "affection" in block.text
    assert "50/100" in block.text


def test_assemble_without_user_card_omits_user_section():
    block = assemble_persona_block(_character(), None)
    assert "[USER CARD]" not in block.text
    assert "[CHARACTER CARD]" in block.text
    assert block.user_card_id is None


def test_assemble_with_empty_dialogues_omits_example_section():
    block = assemble_persona_block(_character(example_dialogues=[]), None)
    assert "[EXAMPLE DIALOGUES]" not in block.text


def test_assemble_with_dialogues_includes_them():
    block = assemble_persona_block(
        _character(example_dialogues=[{"user": "hi", "assistant": "hello"}]),
        None,
    )
    assert "[EXAMPLE DIALOGUES]" in block.text
    assert "user: hi" in block.text
    assert "assistant: hello" in block.text


def test_assemble_raises_when_character_is_none():
    import pytest
    with pytest.raises(PersonaMissingError):
        assemble_persona_block(None, _user())

# SPDX-License-Identifier: MIT
from __future__ import annotations

from src.memory.session_store import MessageRow
from src.server.group_engine import (
    UNKNOWN_SPEAKER,
    format_group_history,
    turn_instruction,
)


def _msg(role: str, content: str, char_id: int | None = None) -> MessageRow:
    return MessageRow(id=1, session_id="s", role=role, content=content,
                      character_card_id=char_id)


def test_assistant_messages_get_speaker_prefix() -> None:
    out = format_group_history(
        [_msg("assistant", "There is a clue.", 7)],
        names_by_id={7: "Mira"}, user_name="tester",
    )
    assert out == [{"role": "assistant", "content": "[Mira]: There is a clue."}]


def test_user_messages_use_room_user_card_name() -> None:
    out = format_group_history(
        [_msg("user", "What do you see?")],
        names_by_id={7: "Mira"}, user_name="tester",
    )
    assert out == [{"role": "user", "content": "[tester]: What do you see?"}]


def test_deleted_character_falls_back_to_placeholder() -> None:
    out = format_group_history(
        [_msg("assistant", "gone", 99)],
        names_by_id={}, user_name="tester",
    )
    assert out == [{"role": "assistant", "content": f"[{UNKNOWN_SPEAKER}]: gone"}]


def test_legacy_message_without_speaker_uses_unknown() -> None:
    out = format_group_history(
        [_msg("assistant", "old")],
        names_by_id={7: "Mira"}, user_name="tester",
    )
    assert out[0]["content"] == f"[{UNKNOWN_SPEAKER}]: old"


def test_order_is_preserved() -> None:
    out = format_group_history(
        [_msg("user", "a"), _msg("assistant", "b", 7)],
        names_by_id={7: "Mira"}, user_name="tester",
    )
    assert [m["role"] for m in out] == ["user", "assistant"]
    assert [m["content"] for m in out] == ["[tester]: a", "[Mira]: b"]


def test_empty_user_name_falls_back_to_user() -> None:
    out = format_group_history(
        [_msg("user", "hi")], names_by_id={}, user_name="",
    )
    assert out[0]["content"] == "[user]: hi"


def test_empty_history() -> None:
    assert format_group_history([], names_by_id={}, user_name="tester") == []


def test_turn_instruction_wraps_a_third_party_trigger() -> None:
    """A bare transcript line would read as more script to continue, so the
    trigger goes back as an instruction naming its speaker."""
    out = turn_instruction("watch out", "Kai")
    assert "Kai" in out
    assert "watch out" in out
    assert "only your own next line" in out


def test_turn_instruction_passes_the_opening_line_through() -> None:
    assert turn_instruction("look around", "") == "look around"

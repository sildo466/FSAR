# SPDX-License-Identifier: MIT
from __future__ import annotations

from src.memory.session_store import MessageRow
from src.server.group_engine import (
    UNKNOWN_SPEAKER,
    format_group_history,
    strip_speaker_marker,
    strip_tool_call_markup,
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
    assert "only your own line" in out


def test_turn_instruction_passes_the_opening_line_through() -> None:
    assert turn_instruction("look around", "") == "look around"


def test_strip_speaker_marker_removes_the_own_name_prefix() -> None:
    assert strip_speaker_marker("[Mira]: 你耳朵有问题", "Mira") == "你耳朵有问题"


def test_strip_speaker_marker_removes_repeated_prefixes() -> None:
    """The copy compounds over rounds, so clearing once is not enough."""
    assert strip_speaker_marker("[Mira]: [Mira]: 双层", "Mira") == "双层"


def test_strip_speaker_marker_handles_width_and_spacing() -> None:
    assert strip_speaker_marker("  [ Mira ] ： 说话", "Mira") == "说话"


def test_strip_speaker_marker_does_not_claim_other_brackets() -> None:
    """Only the speaker's own name is a marker; stage directions survive."""
    raw = "[笑]：你这人真有意思"
    assert strip_speaker_marker(raw, "Mira") == raw


def test_strip_speaker_marker_ignores_another_characters_marker() -> None:
    raw = "[Kai]: not mine to say"
    assert strip_speaker_marker(raw, "Mira") == raw


def test_strip_speaker_marker_is_a_noop_without_a_name() -> None:
    assert strip_speaker_marker("[Mira]: x", "") == "[Mira]: x"


def test_strip_speaker_marker_leaves_clean_text_alone() -> None:
    assert strip_speaker_marker("就是字面意思。", "Mira") == "就是字面意思。"


def test_strip_tool_call_removes_a_well_formed_block() -> None:
    raw = '<tool_call>{"name":"update_emotion"}</tool_call>我说完了'
    assert strip_tool_call_markup(raw) == "我说完了"


def test_strip_tool_call_removes_a_block_in_the_middle() -> None:
    raw = "先说一句<tool_call>{}</tool_call>再说一句"
    assert strip_tool_call_markup(raw) == "先说一句再说一句"


def test_strip_tool_call_removes_a_truncated_block() -> None:
    """A cancelled stream can cut the closing tag off."""
    raw = '正文<tool_call>{"name":"update_emotion"'
    assert strip_tool_call_markup(raw) == "正文"


def test_strip_tool_call_handles_function_call_tags() -> None:
    assert strip_tool_call_markup("<function_call>x</function_call>ok") == "ok"


def test_strip_tool_call_leaves_normal_text_alone() -> None:
    raw = "我用了括号（笑），没别的"
    assert strip_tool_call_markup(raw) == raw


def test_turn_instruction_does_not_imply_the_remark_was_aimed_at_you() -> None:
    """Bystanders answered as the injured party because "Reply now" framed the
    preceding remark as addressed to whoever was picked to speak."""
    out = turn_instruction("你这人真无聊", "Mira")
    assert "not necessarily aimed at you" in out
    assert "Reply now" not in out

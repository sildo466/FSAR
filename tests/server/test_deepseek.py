# SPDX-License-Identifier: Apache-2.0
"""Tests for the DeepSeek-specific request adapter."""
from __future__ import annotations

from types import SimpleNamespace

from src.providers.llm.deepseek import (
    extra_body_for_thinking,
    is_deepseek_official,
    prepare_messages,
)


def test_is_deepseek_official_matches_first_party_hosts():
    assert is_deepseek_official("https://api.deepseek.com/v1") is True
    assert is_deepseek_official("https://api.deepseek.com/") is True
    assert is_deepseek_official("HTTPS://API.DEEPSEEK.COM/v1") is True


def test_is_deepseek_official_rejects_others():
    assert is_deepseek_official("") is False
    assert is_deepseek_official("https://api.openai.com/v1") is False
    assert is_deepseek_official("https://api.deepseek.com.example.com/v1") is False


def test_extra_body_for_thinking_enables_mode():
    assert extra_body_for_thinking() == {"thinking": {"type": "enabled"}}


def test_prepare_messages_preserves_reasoning_content_from_sdk_message():
    msg = SimpleNamespace(
        role="assistant",
        content="final answer",
        reasoning_content="thoughts",
        tool_calls=None,
    )
    out = prepare_messages([msg])
    assert out == [{
        "role": "assistant",
        "content": "final answer",
        "reasoning_content": "thoughts",
        "tool_calls": None,
    }]


def test_prepare_messages_passes_dict_through():
    d = {"role": "assistant", "content": "x"}
    out = prepare_messages([d])
    assert out == [d]

# SPDX-License-Identifier: MIT
import pytest

from src.providers.llm.thinking import EFFORT_LEVELS, resolve_thinking_payload


def test_effort_levels_constant():
    assert EFFORT_LEVELS == ("off", "low", "medium", "high", "xhigh", "max")


@pytest.mark.parametrize(
    "family,model,effort,base_url,expected",
    [
        ("google", "gemini-3-pro", "off", "", None),
        ("anthropic", "claude-opus-4", "off", "", None),
        ("openai_compat", "o3-mini", "off", "https://api.openai.com/v1", None),
        ("google", "gemini-3-pro", "low", "", {"generationConfig": {"thinkingConfig": {"thinkingLevel": "LOW"}}}),
        ("google", "gemini-3-pro", "medium", "", {"generationConfig": {"thinkingConfig": {"thinkingLevel": "MEDIUM"}}}),
        ("google", "gemini-3-pro", "high", "", {"generationConfig": {"thinkingConfig": {"thinkingLevel": "HIGH"}}}),
        ("google", "gemini-3-pro", "xhigh", "", {"generationConfig": {"thinkingConfig": {"thinkingLevel": "HIGH"}}}),
        ("google", "gemini-3-pro", "max", "", {"generationConfig": {"thinkingConfig": {"thinkingLevel": "HIGH"}}}),
        ("google", "gemini-2.5-pro", "low", "", {"generationConfig": {"thinkingConfig": {"thinkingBudget": 1024}}}),
        ("google", "gemini-2.5-pro", "medium", "", {"generationConfig": {"thinkingConfig": {"thinkingBudget": 8192}}}),
        ("google", "gemini-2.5-pro", "high", "", {"generationConfig": {"thinkingConfig": {"thinkingBudget": 24576}}}),
        ("google", "gemini-2.5-pro", "xhigh", "", {"generationConfig": {"thinkingConfig": {"thinkingBudget": 32768}}}),
        ("google", "gemini-2.5-pro", "max", "", {"generationConfig": {"thinkingConfig": {"thinkingBudget": 65536}}}),
        ("google", "gemini-1.5-flash", "high", "", None),
        ("openai_compat", "deepseek-chat", "low", "https://api.deepseek.com/v1", {"thinking": {"type": "enabled"}}),
        ("openai_compat", "deepseek-chat", "max", "https://api.deepseek.com/v1", {"thinking": {"type": "enabled"}}),
        ("openai_compat", "o3-mini", "low", "https://api.openai.com/v1", {"reasoning_effort": "low"}),
        ("openai_compat", "o3-mini", "medium", "https://api.openai.com/v1", {"reasoning_effort": "medium"}),
        ("openai_compat", "o3-mini", "high", "https://api.openai.com/v1", {"reasoning_effort": "high"}),
        ("openai_compat", "o3-mini", "xhigh", "https://api.openai.com/v1", {"reasoning_effort": "high"}),
        ("openai_compat", "o1-preview", "max", "https://api.openai.com/v1", {"reasoning_effort": "high"}),
        ("openai_compat", "gpt-4o", "high", "https://api.openai.com/v1", None),
        ("openai_compat", "o3-mini", "high", "https://openrouter.ai/api/v1", None),
        ("anthropic", "claude-opus-4", "low", "", {"thinking": {"type": "enabled", "budget_tokens": 1024}}),
        ("anthropic", "claude-opus-4", "medium", "", {"thinking": {"type": "enabled", "budget_tokens": 4096}}),
        ("anthropic", "claude-opus-4", "high", "", {"thinking": {"type": "enabled", "budget_tokens": 8192}}),
        ("anthropic", "claude-opus-4", "xhigh", "", {"thinking": {"type": "enabled", "budget_tokens": 16384}}),
        ("anthropic", "claude-opus-4", "max", "", {"thinking": {"type": "enabled", "budget_tokens": 32768}}),
        ("google", "gemini-3-pro", "foobar", "", None),
        ("anthropic", "claude-opus-4", "", "", None),
    ],
)
def test_resolve_thinking_payload(family, model, effort, base_url, expected):
    assert resolve_thinking_payload(family, model, effort, base_url) == expected

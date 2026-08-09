# SPDX-License-Identifier: MIT
"""Map UI model-thinking-effort levels to provider-native request fields."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from src.providers.llm.deepseek import is_deepseek_official


EFFORT_LEVELS: tuple[str, ...] = ("off", "low", "medium", "high", "xhigh", "max")

_GEMINI3_LEVEL_MAP: dict[str, str] = {
    "low": "LOW",
    "medium": "MEDIUM",
    "high": "HIGH",
    "xhigh": "HIGH",
    "max": "HIGH",
}

_GEMINI25_BUDGET_MAP: dict[str, int] = {
    "low": 1024,
    "medium": 8192,
    "high": 24576,
    "xhigh": 32768,
    "max": 65536,
}

_OPENAI_REASONING_MAP: dict[str, str] = {
    "low": "low",
    "medium": "medium",
    "high": "high",
    "xhigh": "high",
    "max": "high",
}

_ANTHROPIC_BUDGET_MAP: dict[str, int] = {
    "low": 1024,
    "medium": 4096,
    "high": 8192,
    "xhigh": 16384,
    "max": 32768,
}

_GEMINI3_MODEL_PREFIXES = ("gemini-3",)
_GEMINI25_MODEL_PREFIXES = ("gemini-2.5",)
_OPENAI_O_SERIES_PREFIXES = ("o1", "o3", "o4-mini", "gpt-5")
_OPENAI_OFFICIAL_HOSTS = {"api.openai.com"}


def _is_openai_o_series(model_id: str, base_url: str) -> bool:
    if not base_url:
        return False
    try:
        host = (urlparse(base_url).hostname or "").lower()
    except ValueError:
        return False
    if host not in _OPENAI_OFFICIAL_HOSTS:
        return False
    model = model_id.lower()
    return any(model.startswith(prefix) for prefix in _OPENAI_O_SERIES_PREFIXES)


def resolve_thinking_payload(
    provider_family: str,
    model_id: str,
    effort: str,
    base_url: str = "",
) -> dict[str, Any] | None:
    """Return the provider payload, or None when effort is unsupported."""
    if not isinstance(effort, str) or effort not in EFFORT_LEVELS:
        return None
    if effort == "off":
        return None

    family = (provider_family or "").strip().lower()
    model = (model_id or "").strip().lower()

    if family == "google":
        if any(model.startswith(prefix) for prefix in _GEMINI3_MODEL_PREFIXES):
            level = _GEMINI3_LEVEL_MAP.get(effort)
            if level is None:
                return None
            return {"generationConfig": {"thinkingConfig": {"thinkingLevel": level}}}
        if any(model.startswith(prefix) for prefix in _GEMINI25_MODEL_PREFIXES):
            budget = _GEMINI25_BUDGET_MAP.get(effort)
            if budget is None:
                return None
            return {"generationConfig": {"thinkingConfig": {"thinkingBudget": budget}}}
        return None

    if family == "openai_compat":
        if is_deepseek_official(base_url):
            return {"thinking": {"type": "enabled"}}
        if _is_openai_o_series(model, base_url):
            return {"reasoning_effort": _OPENAI_REASONING_MAP[effort]}
        return None

    if family == "anthropic":
        budget = _ANTHROPIC_BUDGET_MAP.get(effort)
        if budget is None:
            return None
        return {"thinking": {"type": "enabled", "budget_tokens": budget}}

    return None

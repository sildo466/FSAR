# SPDX-License-Identifier: MIT
"""ASR adapter registry."""

from typing import Any

from .openai_compat import OpenAICompatAsrAdapter
from .volcengine import VolcengineAsrAdapter

_REGISTRY: dict[str, Any] = {
    "openai_compat": OpenAICompatAsrAdapter(),
    "volcengine": VolcengineAsrAdapter(),
}


def register(family: str, adapter: Any) -> None:
    _REGISTRY[family] = adapter


def get_adapter(family: str) -> Any:
    if family not in _REGISTRY:
        raise KeyError(f"unknown asr family: {family}")
    return _REGISTRY[family]


__all__ = ["get_adapter", "register"]

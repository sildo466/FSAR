# SPDX-License-Identifier: MIT
"""TTS adapter registry."""

from typing import Any

from .azure import AzureAdapter
from .dashscope import DashScopeAdapter
from .edge import EdgeAdapter
from .elevenlabs import ElevenLabsAdapter
from .minimax import MiniMaxAdapter
from .openai_compat import OpenAICompatAdapter
from .volcengine import VolcengineAdapter

_REGISTRY: dict[str, Any] = {
    "edge": EdgeAdapter(),
    "openai_compat": OpenAICompatAdapter(),
    "elevenlabs": ElevenLabsAdapter(),
    "azure": AzureAdapter(),
    "dashscope": DashScopeAdapter(),
    "volcengine": VolcengineAdapter(),
    "minimax": MiniMaxAdapter(),
}


def register(family: str, adapter: Any) -> None:
    _REGISTRY[family] = adapter


def get_adapter(family: str) -> Any:
    if family not in _REGISTRY:
        raise KeyError(f"unknown tts family: {family}")
    return _REGISTRY[family]


__all__ = ["get_adapter", "register"]

# SPDX-License-Identifier: MIT
"""Text-to-speech provider stack."""

from .adapters.base import TtsError
from .dispatch import tts_synthesize

__all__ = ["TtsError", "tts_synthesize"]

# SPDX-License-Identifier: MIT
"""Automatic speech recognition provider stack."""

from .adapters.base import AsrError
from .dispatch import asr_transcribe

__all__ = ["AsrError", "asr_transcribe"]

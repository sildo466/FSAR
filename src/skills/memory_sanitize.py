from __future__ import annotations

import re
from dataclasses import dataclass

from src.utils.logger import logger


DEFAULT_PATTERNS = [
    r"\bignore\s+(?:all\s+|any\s+|the\s+)?(?:previous|prior|above)\s+instructions?\b",
    r"\byou\s+are\s+now\b",
    r"<\|(?:im_start|im_end|system|assistant|user)\|>",
    r"\[/?(?:system|assistant|developer)\]",
    r"\bsystem\s+prompt\b",
]


@dataclass(frozen=True)
class SanitizeResult:
    allowed: bool
    matches: tuple[str, ...] = ()


class MemorySanitizationError(ValueError):
    pass


class Sanitizer:
    def __init__(self, config) -> None:
        self.enabled = bool(
            config.get("security.memory.write_sanitization.enabled", True)
        )
        self.block_on_match = bool(
            config.get("security.memory.write_sanitization.block_on_match", True)
        )
        patterns = [
            *DEFAULT_PATTERNS,
            *(config.get("security.memory.write_sanitization.custom_patterns", []) or []),
        ]
        self.patterns: list[tuple[str, re.Pattern[str]]] = []
        for raw in patterns:
            if not isinstance(raw, str):
                continue
            try:
                self.patterns.append((raw, re.compile(raw, re.IGNORECASE)))
            except re.error:
                continue

    def check(self, body: str) -> SanitizeResult:
        if not self.enabled:
            return SanitizeResult(True)
        matches = tuple(raw for raw, pattern in self.patterns if pattern.search(body))
        if not matches:
            return SanitizeResult(True)
        if not self.block_on_match:
            logger.warning(f"memory sanitization warning: {len(matches)} pattern(s) matched")
            return SanitizeResult(True, matches)
        return SanitizeResult(False, matches)

    def enforce(self, body: str) -> None:
        result = self.check(body)
        if not result.allowed:
            raise MemorySanitizationError("memory sanitization flagged")


def sanitize(body: str, config) -> SanitizeResult:
    return Sanitizer(config).check(body)


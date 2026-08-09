from __future__ import annotations

import re
from typing import Any


DEFAULT_PATTERNS = [
    r"sk-(?:or-|ant-|cp-|proj-)?[A-Za-z0-9_-]{20,}",
    r"AKIA[A-Z0-9]{16}",
    r"ghp_[A-Za-z0-9]{36}",
    r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{64,}={0,2}(?![A-Za-z0-9+/])",
]


class Redactor:
    def __init__(self, config) -> None:
        self.enabled = bool(config.get("security.redaction.enabled", True))
        self.max_length = max(
            1, int(config.get("security.redaction.max_string_length", 16384))
        )
        patterns = [*DEFAULT_PATTERNS, *(config.get("security.redaction.patterns", []) or [])]
        self.patterns: list[re.Pattern[str]] = []
        for pattern in patterns:
            if not isinstance(pattern, str):
                continue
            try:
                self.patterns.append(re.compile(pattern))
            except re.error:
                continue

    def redact(self, value: Any) -> Any:
        if not self.enabled:
            return value
        if isinstance(value, str):
            result = value[: self.max_length]
            for pattern in self.patterns:
                result = pattern.sub("[REDACTED:api_key_pattern]", result)
            return result
        if isinstance(value, list):
            return [self.redact(item) for item in value]
        if isinstance(value, tuple):
            return tuple(self.redact(item) for item in value)
        if isinstance(value, dict):
            return {key: self.redact(item) for key, item in value.items()}
        return value


def redact(value: Any, config) -> Any:
    return Redactor(config).redact(value)


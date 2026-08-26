from __future__ import annotations

import re
from typing import Any


DEFAULT_PATTERNS = [
    r"sk-(?:or-|ant-|cp-|proj-)?[A-Za-z0-9_-]{20,}",
    r"AKIA[A-Z0-9]{16}",
    r"ghp_[A-Za-z0-9]{36}",
    r"(?i)(?:api[_-]?key|access[_-]?key|secret(?:[_-]?key)?|token|passwd|password|authorization)\s*[:=]\s*[A-Za-z0-9_+./-]{16,}",
]

# Continuous base64 blobs (screenshots, images, binaries) are payloads, not
# keys. Redaction stops at string boundaries so such blobs are never scanned:
# a pure base64 run longer than this is treated as binary data.
_PAYLOAD_BASE64 = re.compile(r"^[A-Za-z0-9+/]+={0,2}$")
_PAYLOAD_MIN_B64 = 64


class Redactor:
    """Mask API-key-like secrets in tool output.

    Two design rules:
    1. Never truncate strings — tool results (screenshots, large file reads)
       must round-trip intact.
    2. Never scan binary payloads — a continuous base64 blob (e.g. a
       screenshot) is data, not a key, and is passed through unchanged.
    """

    def __init__(self, config) -> None:
        self.enabled = bool(config.get("security.redaction.enabled", True))
        patterns = [*DEFAULT_PATTERNS, *(config.get("security.redaction.patterns", []) or [])]
        self.patterns: list[re.Pattern[str]] = []
        for pattern in patterns:
            if not isinstance(pattern, str):
                continue
            try:
                self.patterns.append(re.compile(pattern))
            except re.error:
                continue

    @staticmethod
    def _is_binary_payload(value: str) -> bool:
        if len(value) < _PAYLOAD_MIN_B64:
            return False
        stripped = value.strip()
        if stripped.startswith("data:"):
            return True
        return bool(_PAYLOAD_BASE64.fullmatch(stripped))

    def redact(self, value: Any) -> Any:
        if not self.enabled:
            return value
        if isinstance(value, str):
            if self._is_binary_payload(value):
                return value
            result = value
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
# SPDX-License-Identifier: MIT
"""Token buckets with a bounded key table.

Unauthenticated keys are attacker-chosen (a source address), so the table has
to be capped. Over the cap, new keys share one overflow bucket: an attack
costs fairness under load, never unbounded memory.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

OVERFLOW_KEY = "__overflow__"


@dataclass
class _Bucket:
    tokens: float
    updated: float


class RateBudget:
    def __init__(self, max_keys: int = 4096) -> None:
        self.max_keys = max(1, int(max_keys))
        self._buckets: dict[str, _Bucket] = {}

    def tracked_keys(self) -> int:
        return len(self._buckets)

    def reset(self) -> None:
        self._buckets.clear()

    def _resolve_key(self, key: str) -> str:
        if key in self._buckets:
            return key
        if len(self._buckets) >= self.max_keys:
            return OVERFLOW_KEY
        return key

    def allow(
        self,
        key: str,
        *,
        limit: int,
        per_seconds: float,
        burst: int = 1,
        now: float | None = None,
    ) -> bool:
        """Consume one unit from `key`'s bucket, or refuse when it is empty."""
        current = time.monotonic() if now is None else now
        capacity = max(1.0, float(burst))
        # Guard only against a zero or negative window. Clamping it up to a
        # second would silently make every sub-second budget stricter than
        # configured, which is a wrong answer rather than a safe one.
        rate = max(0.0, float(limit)) / max(1e-6, float(per_seconds))

        resolved = self._resolve_key(key)
        bucket = self._buckets.get(resolved)
        if bucket is None:
            bucket = _Bucket(tokens=capacity, updated=current)
            self._buckets[resolved] = bucket
        else:
            elapsed = max(0.0, current - bucket.updated)
            bucket.tokens = min(capacity, bucket.tokens + elapsed * rate)
            bucket.updated = current

        if bucket.tokens < 1.0:
            return False
        bucket.tokens -= 1.0
        return True

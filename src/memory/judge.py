# SPDX-License-Identifier: MIT
"""Per-candidate relevance judgment for memory injection."""

from __future__ import annotations

from typing import Protocol

from src.memory.candidates import Candidate


class MemoryJudge(Protocol):
    def score(
        self,
        query: str,
        candidates: list[Candidate],
        *,
        mode: str,
        context: str = "",
    ) -> dict[str, float]:
        """Return key -> 0..1 (higher = more worth injecting). Empty dict = no judgment."""
        ...


class NullJudge:
    """No judgment: the packer falls back to static priority order."""

    def score(self, query, candidates, *, mode, context=""):
        return {}

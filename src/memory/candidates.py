# SPDX-License-Identifier: MIT
"""Turn recall results into individually judgeable injection candidates."""

from __future__ import annotations

from dataclasses import dataclass

from src.memory.recall import RecallResult

PRIORITY = {
    "fact": 0,
    "profile": 1,
    "preference": 2,
    "strategy": 2,
    "pattern": 3,
    "experience": 3,
    "history": 4,
}


@dataclass(frozen=True)
class Candidate:
    source: str
    key: str
    text: str
    priority: int

    @property
    def chars(self) -> int:
        return len(self.text)


def candidates_from_recall(result: RecallResult) -> list[Candidate]:
    out: list[Candidate] = []

    for i, c in enumerate(result.memory_chunks, start=1):
        out.append(Candidate("fact", f"F{i}", f"- {c['title']}: {c['body']}", PRIORITY["fact"]))
    for i, (k, v) in enumerate(result.profile.items(), start=1):
        out.append(Candidate("profile", f"U{i}", f"- {k}: {v}", PRIORITY["profile"]))
    for i, (k, v) in enumerate(result.preferences.items(), start=1):
        out.append(Candidate("preference", f"R{i}", f"- {k}: {v}", PRIORITY["preference"]))
    for i, p in enumerate(result.patterns, start=1):
        out.append(Candidate("pattern", f"T{i}", f"- {p['pattern']} (x{p['count']})", PRIORITY["pattern"]))
    for i, c in enumerate(result.similar_conversations, start=1):
        out.append(Candidate("history", f"H{i}", f"- {c.get('text', '')}", PRIORITY["history"]))

    return out

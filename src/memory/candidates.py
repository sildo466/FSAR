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


def cap_by_source(candidates: list[Candidate], cap: int) -> list[Candidate]:
    """Keep at most `cap` candidates, taking turns across sources.

    Round-robin rather than priority order: history sits at the lowest priority
    but holds most query-relevant recall, so a priority cut would drop it
    before the judge ever sees it.
    """
    if cap <= 0:
        return []
    if len(candidates) <= cap:
        return list(candidates)

    buckets: dict[str, list[Candidate]] = {}
    for c in candidates:
        buckets.setdefault(c.source, []).append(c)

    kept: list[Candidate] = []
    cursor = {src: 0 for src in buckets}
    while len(kept) < cap:
        progressed = False
        for src, items in buckets.items():
            if cursor[src] < len(items):
                kept.append(items[cursor[src]])
                cursor[src] += 1
                progressed = True
                if len(kept) >= cap:
                    break
        if not progressed:
            break
    return kept


def candidates_from_experience(store, *, max_desc_chars: int = 60) -> list[Candidate]:
    """Experience index entries as candidates.

    Descriptions stay short (60 chars by default) which is what lets this source
    afford to enter the pool without a count limit.
    """
    out: list[Candidate] = []
    for i, exp in enumerate(store.list_for_index(), start=1):
        desc = (exp.description or "").strip().replace("\n", " ")[:max_desc_chars]
        text = f"- {exp.name}: {desc}" if desc else f"- {exp.name}"
        out.append(Candidate("experience", f"E{i}", text, PRIORITY["experience"]))
    return out


def candidates_from_strategy(injector) -> list[Candidate]:
    """Judgeable strategy lines. Tool stats are deliberately not included —
    they are operational warnings that build_block() injects unconditionally."""
    out: list[Candidate] = []
    for i, line in enumerate(injector.item_lines(), start=1):
        out.append(Candidate("strategy", f"S{i}", line, PRIORITY["strategy"]))
    return out

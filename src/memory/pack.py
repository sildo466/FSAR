# SPDX-License-Identifier: MIT
"""Atomic budget packing for injection candidates."""

from __future__ import annotations

from dataclasses import replace

from src.memory.candidates import Candidate


def pack(
    candidates: list[Candidate],
    scores: dict[str, float],
    *,
    budget_chars: int,
    score_floor: float,
    max_item_chars: int,
) -> list[Candidate]:
    """Select whole candidates until the character budget is exhausted.

    Nothing is cut mid-item; the only truncation is a single item that alone
    exceeds `max_item_chars`. When the floor leaves budget unused, that is
    intended — injecting junk to fill space is worse than injecting less.
    """
    ordered = sorted(
        candidates,
        key=lambda k: (-scores.get(k.key, 0.0), k.priority),
    )

    kept: list[Candidate] = []
    used = 0
    for item in ordered:
        if scores and scores.get(item.key, 0.0) < score_floor:
            continue
        if item.chars > max_item_chars:
            item = replace(item, text=item.text[:max_item_chars])
        if used + item.chars > budget_chars:
            continue
        kept.append(item)
        used += item.chars
    return kept


_MEMORY_HEADERS = {
    "fact": "[Saved Facts]",
    "profile": "[User Profile]",
    "preference": "[Known Preferences]",
    "pattern": "[Behavioral Patterns]",
    "history": "[Relevant History]",
}
_MEMORY_ORDER = ["fact", "profile", "preference", "pattern", "history"]


def render_slots(packed: list[Candidate]) -> dict[str, str]:
    """Render packed candidates back into the three prompt slots, grouped by source.

    Packing decides which items are injected; rendering decides where they land.
    Grouping by source keeps the section headers intact — laying items out in
    score order would interleave and repeat them.
    """
    by_source: dict[str, list[Candidate]] = {}
    for item in packed:
        by_source.setdefault(item.source, []).append(item)

    memory_parts: list[str] = []
    for source in _MEMORY_ORDER:
        items = by_source.get(source)
        if not items:
            continue
        memory_parts.append(_MEMORY_HEADERS[source])
        memory_parts.extend(i.text for i in items)

    strategy_items = by_source.get("strategy", [])
    experience_items = by_source.get("experience", [])

    strategy = ""
    if strategy_items:
        strategy = "## Learned Strategies (from past interactions)\n" + "\n".join(
            i.text for i in strategy_items
        ) + "\n"

    experience = ""
    if experience_items:
        experience = "## Experiences\n" + "\n".join(i.text for i in experience_items) + "\n"

    return {
        "memory": "\n".join(memory_parts),
        "strategy": strategy,
        "experience": experience,
    }

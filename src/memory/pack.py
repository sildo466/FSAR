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
    drop_unscored: bool = False,
) -> list[Candidate]:
    """Select whole candidates until the character budget is exhausted.

    Nothing is cut mid-item; the only truncation is a single item that alone
    exceeds `max_item_chars`. When the floor leaves budget unused, that is
    intended — injecting junk to fill space is worse than injecting less.

    A key missing from `scores` means the judge did not rate it — no judge at
    all, or a batch that died. Such items keep priority order and skip the
    floor, so a partial judge failure degrades to priority rather than dropping
    them. `drop_unscored=True` inverts that for character mode, where an
    unjudged item must not reach the prompt unfiltered.
    """
    ordered = sorted(
        candidates,
        key=lambda k: (-scores.get(k.key, 0.0), k.priority),
    )

    kept: list[Candidate] = []
    used = 0
    for item in ordered:
        if item.key in scores:
            if scores[item.key] < score_floor:
                continue
        elif drop_unscored:
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


def render_slots(
    packed: list[Candidate],
    *,
    extra_strategy_lines: list[str] = (),
    experience_header: str = "## Experiences",
    experience_rule: str = "",
    extra_experience_blocks: list[str] = (),
) -> dict[str, str]:
    """Render packed candidates back into the three prompt slots, grouped by source.

    Packing decides which items are injected; rendering decides where they land.
    Grouping by source keeps the section headers intact — laying items out in
    score order would interleave and repeat them.

    Three things ride outside the pool on purpose, because they are contracts
    rather than content and must never be scored away:

    - `extra_strategy_lines` — tool-stat warnings.
    - `experience_header` / `experience_rule` — the skill-loading contract. The
      rule only appears when at least one entry survived, since it refers to the
      list above it.
    - `extra_experience_blocks` — the memory-chunks block at medium/high.
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

    strategy_lines = list(extra_strategy_lines)
    strategy_lines.extend(i.text for i in by_source.get("strategy", []))
    strategy = ""
    if strategy_lines:
        strategy = "## Learned Strategies (from past interactions)\n" + "\n".join(
            strategy_lines
        ) + "\n"

    experience_items = by_source.get("experience", [])
    index_lines: list[str] = []
    if experience_items:
        index_lines.append(experience_header)
        index_lines.extend(i.text for i in experience_items)
        if experience_rule:
            index_lines.append(experience_rule)
    experience_parts = ["\n".join(index_lines)] if index_lines else []
    experience_parts.extend(b for b in extra_experience_blocks if b)
    experience = ("\n\n".join(experience_parts) + "\n") if experience_parts else ""

    return {
        "memory": "\n".join(memory_parts),
        "strategy": strategy,
        "experience": experience,
    }

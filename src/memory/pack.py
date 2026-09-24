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

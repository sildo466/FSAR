# SPDX-License-Identifier: MIT
"""Candidate -> judge -> pack -> render: the single injection path for both modes."""

from __future__ import annotations

from dataclasses import dataclass

from src.memory.candidates import (
    Candidate,
    candidates_from_experience,
    candidates_from_recall,
    candidates_from_strategy,
    cap_by_source,
)
from src.memory.judge import MemoryJudge
from src.memory.pack import pack, render_slots
from src.memory.recall import RecallResult


@dataclass
class InjectionPipeline:
    judge: MemoryJudge
    budget_chars: int
    candidate_cap: int
    score_floor: float
    max_item_chars: int

    def build_slots(
        self,
        query: str,
        recall_result: RecallResult,
        *,
        mode: str,
        context: str = "",
        experience_store=None,
        strategy_injector=None,
        include_extra: bool = True,
        fail_closed: bool = False,
    ) -> dict[str, str]:
        """Build the three prompt slots from one shared candidate pool and budget.

        `include_extra=False` skips the strategy and experience sources for
        callers that only consume the memory slot, so they do not pay for
        judgments whose results they discard.

        `fail_closed=True` injects nothing when the judge produced no scores.
        Character mode needs this: its persona filter exists to keep technical
        memory out of the prompt, and falling back to priority order would leak
        exactly the items it is meant to remove.
        """
        candidates: list[Candidate] = candidates_from_recall(recall_result)
        tool_stats: list[str] = []

        if include_extra and strategy_injector is not None:
            candidates.extend(candidates_from_strategy(strategy_injector))
            tool_stats = strategy_injector.tool_stat_lines()
        if include_extra and experience_store is not None:
            candidates.extend(candidates_from_experience(experience_store))

        capped = cap_by_source(candidates, self.candidate_cap)
        scores = self.judge.score(query, capped, mode=mode, context=context)
        if fail_closed and capped and not scores:
            return {"memory": "", "strategy": "", "experience": ""}

        packed = pack(
            capped,
            scores,
            budget_chars=self.budget_chars,
            score_floor=self.score_floor,
            max_item_chars=self.max_item_chars,
        )
        return render_slots(packed, extra_strategy_lines=tool_stats)

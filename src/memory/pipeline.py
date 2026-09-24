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
        experience_header: str = "## Experiences",
        experience_rule: str = "",
        extra_experience_blocks=(),
    ) -> dict[str, str]:
        """Build the three prompt slots from one shared candidate pool and budget.

        `include_extra=False` skips the strategy and experience sources for
        callers that only consume the memory slot, so they do not pay for
        judgments whose results they discard.

        `fail_closed=True` (character mode) drops any candidate the judge did
        not rate, including the whole pool when the judge failed outright. The
        persona filter exists to keep technical recall out of the prompt, so
        falling back to priority order would leak exactly what it removes.
        Agent mode keeps that fallback, where unfiltered recall is intended.

        `experience_header` / `experience_rule` / `extra_experience_blocks` are
        contracts rather than content: they ride outside the pool so scoring can
        never drop them. The rule is only rendered when an entry survived, since
        it refers to the list above it.
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
        packed = pack(
            capped,
            scores,
            budget_chars=self.budget_chars,
            score_floor=self.score_floor,
            max_item_chars=self.max_item_chars,
            drop_unscored=fail_closed,
        )
        return render_slots(
            packed,
            extra_strategy_lines=tool_stats,
            experience_header=experience_header,
            experience_rule=experience_rule,
            extra_experience_blocks=list(extra_experience_blocks),
        )

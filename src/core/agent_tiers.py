# SPDX-License-Identifier: MIT
"""Manual capability tiers for the shared agent loop."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TierProfile:
    name: str
    max_tool_turns: int
    inject_strategy: bool
    inject_experience: bool
    semantic_recall: bool
    recall_top_k: int
    injector_intensity: str
    thinking: bool
    post_reflection: bool
    slim_system_prompt: bool
    todo_planning: bool
    parallel_tools: bool
    verify_selfcheck: bool
    verify_max: int
    subagent: bool
    subagent_max: int
    subagent_autonomous: bool
    per_step_reflect: bool
    reflect_every_n: int
    reflect_on_error: bool
    dynamic_recall: bool
    execution_fsm: bool
    subagent_generations: int
    subagent_per_gen: int
    debate_enabled: bool
    shared_experience_pool: bool
    runaway_cutoff: int
    compact_threshold: float


TIER_ORDER = ("low", "medium", "high", "xhigh", "max", "ultra")


def _profile(
    name: str,
    *,
    max_tool_turns: int,
    compact_threshold: float,
    **overrides: object,
) -> TierProfile:
    values: dict[str, object] = {
        "name": name,
        "max_tool_turns": max_tool_turns,
        "inject_strategy": True,
        "inject_experience": True,
        "semantic_recall": True,
        "recall_top_k": 5,
        "injector_intensity": "medium",
        "thinking": True,
        "post_reflection": True,
        "slim_system_prompt": False,
        "todo_planning": False,
        "parallel_tools": False,
        "verify_selfcheck": False,
        "verify_max": 0,
        "subagent": False,
        "subagent_max": 0,
        "subagent_autonomous": False,
        "per_step_reflect": False,
        "reflect_every_n": 0,
        "reflect_on_error": False,
        "dynamic_recall": False,
        "execution_fsm": False,
        "subagent_generations": 0,
        "subagent_per_gen": 0,
        "debate_enabled": False,
        "shared_experience_pool": False,
        "runaway_cutoff": 0,
        "compact_threshold": compact_threshold,
    }
    values.update(overrides)
    return TierProfile(**values)  # type: ignore[arg-type]


TIER_PROFILES = {
    "low": _profile(
        "low",
        max_tool_turns=8,
        compact_threshold=0.60,
        inject_strategy=False,
        inject_experience=False,
        semantic_recall=False,
        recall_top_k=0,
        injector_intensity="off",
        thinking=False,
        post_reflection=False,
        slim_system_prompt=True,
    ),
    "medium": _profile("medium", max_tool_turns=50, compact_threshold=0.75),
    "high": _profile(
        "high",
        max_tool_turns=80,
        compact_threshold=0.75,
        todo_planning=True,
        parallel_tools=True,
        verify_selfcheck=True,
        verify_max=2,
    ),
    "xhigh": _profile(
        "xhigh",
        max_tool_turns=80,
        compact_threshold=0.80,
        todo_planning=True,
        parallel_tools=True,
        verify_selfcheck=True,
        verify_max=2,
        recall_top_k=15,
        injector_intensity="high",
        subagent=True,
        subagent_max=1,
        subagent_generations=1,
        subagent_per_gen=1,
        per_step_reflect=True,
        reflect_every_n=3,
        reflect_on_error=True,
        dynamic_recall=True,
    ),
    "max": _profile(
        "max",
        max_tool_turns=120,
        compact_threshold=0.80,
        todo_planning=True,
        parallel_tools=True,
        verify_selfcheck=True,
        verify_max=2,
        recall_top_k=15,
        injector_intensity="high",
        subagent=True,
        subagent_max=5,
        subagent_autonomous=True,
        subagent_generations=1,
        subagent_per_gen=5,
        per_step_reflect=True,
        reflect_every_n=3,
        reflect_on_error=True,
        dynamic_recall=True,
        execution_fsm=True,
    ),
    "ultra": _profile(
        "ultra",
        max_tool_turns=200,
        compact_threshold=0.85,
        todo_planning=True,
        parallel_tools=True,
        verify_selfcheck=True,
        verify_max=2,
        recall_top_k=15,
        injector_intensity="high",
        subagent=True,
        subagent_max=8,
        subagent_autonomous=True,
        subagent_generations=5,
        subagent_per_gen=8,
        per_step_reflect=True,
        reflect_every_n=1,
        reflect_on_error=True,
        dynamic_recall=True,
        execution_fsm=True,
        debate_enabled=True,
        shared_experience_pool=True,
        runaway_cutoff=3,
    ),
}


def get_tier_profile(value: object) -> TierProfile:
    name = str(value or "medium").strip().lower()
    return TIER_PROFILES.get(name, TIER_PROFILES["medium"])


def is_valid_tier(value: object) -> bool:
    return isinstance(value, str) and value.strip().lower() in TIER_PROFILES

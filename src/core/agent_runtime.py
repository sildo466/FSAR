# SPDX-License-Identifier: MIT
"""Ephemeral state shared by a main agent and its descendants."""

from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from src.core.agent_tiers import TierProfile


@dataclass
class AgentRecord:
    agent_id: str
    parent_id: str | None
    depth: int
    label: str
    assignment: str
    kind: str = "subagent"
    status: str = "queued"


@dataclass
class AgentLoopResult:
    conclusion: str
    outcome: str
    steps: int = 0


@dataclass
class AgentRunState:
    root_task_id: str
    profile: TierProfile
    agents: dict[str, AgentRecord] = field(default_factory=dict)
    generation_counts: dict[int, int] = field(default_factory=lambda: defaultdict(int))
    parent_spawn_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    blackboard: list[dict[str, str]] = field(default_factory=list)
    experience_pool: deque[dict[str, str]] = field(default_factory=lambda: deque(maxlen=40))
    serial_tool_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    state_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    force_convergence: bool = False
    debate_idle_rounds: int = 0
    character: Any = None

    async def reserve_agent(
        self,
        *,
        agent_id: str,
        parent_id: str,
        depth: int,
        label: str,
        assignment: str,
    ) -> AgentRecord | None:
        async with self.state_lock:
            if depth > self.profile.subagent_generations:
                return None
            parent_limit = (
                self.profile.subagent_per_gen
                if self.profile.name == "ultra"
                else self.profile.subagent_max
            )
            if self.parent_spawn_counts[parent_id] >= parent_limit:
                return None
            if self.generation_counts[depth] >= self.profile.subagent_per_gen:
                return None
            record = AgentRecord(agent_id, parent_id, depth, label, assignment)
            self.agents[agent_id] = record
            self.parent_spawn_counts[parent_id] += 1
            self.generation_counts[depth] += 1
            return record

    async def post_blackboard(
        self,
        *,
        agent_id: str,
        entry_type: str,
        content: str,
    ) -> None:
        async with self.state_lock:
            self.blackboard.append({
                "agent_id": agent_id,
                "type": entry_type,
                "content": content[:4000],
            })
            if len(self.blackboard) > 80:
                del self.blackboard[:-80]

    async def remember_step(
        self,
        *,
        agent_id: str,
        tool: str,
        outcome: str,
        result: str,
    ) -> None:
        if not self.profile.shared_experience_pool:
            return
        async with self.state_lock:
            self.experience_pool.append({
                "agent_id": agent_id,
                "tool": tool,
                "outcome": outcome,
                "result": result[:500],
            })

    def render_blackboard(self) -> str:
        if not self.blackboard:
            return ""
        lines = ["## Shared Blackboard"]
        for entry in self.blackboard[-20:]:
            lines.append(
                f"- [{entry['type']}] {entry['agent_id']}: {entry['content']}"
            )
        return "\n".join(lines)

    def render_experience_pool(self) -> str:
        if not self.experience_pool:
            return ""
        lines = ["## Shared Working Experience"]
        for entry in list(self.experience_pool)[-12:]:
            lines.append(
                f"- {entry['agent_id']} / {entry['tool']} / {entry['outcome']}: "
                f"{entry['result']}"
            )
        return "\n".join(lines)

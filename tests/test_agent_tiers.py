from __future__ import annotations

import asyncio
import unittest
from dataclasses import FrozenInstanceError

from src.core.agent_runtime import AgentRunState
from src.core.agent_tiers import TIER_ORDER, TIER_PROFILES, get_tier_profile
from src.memory.decision_log import (
    clear_task_context,
    next_task_context,
    set_task_context,
)


class TierProfileTests(unittest.TestCase):
    def test_default_and_unknown_values_resolve_to_medium(self) -> None:
        self.assertIs(get_tier_profile(None), TIER_PROFILES["medium"])
        self.assertIs(get_tier_profile("unknown"), TIER_PROFILES["medium"])
        self.assertEqual(get_tier_profile(" XHIGH ").name, "xhigh")

    def test_capabilities_are_cumulative_from_medium(self) -> None:
        capabilities = (
            "todo_planning",
            "parallel_tools",
            "verify_selfcheck",
            "subagent",
            "per_step_reflect",
            "dynamic_recall",
            "execution_fsm",
            "debate_enabled",
            "shared_experience_pool",
        )
        profiles = [TIER_PROFILES[name] for name in TIER_ORDER[1:]]
        for capability in capabilities:
            enabled = False
            for profile in profiles:
                current = bool(getattr(profile, capability))
                if enabled:
                    self.assertTrue(current, f"{profile.name} lost {capability}")
                enabled = enabled or current

    def test_profiles_are_frozen_and_turn_caps_increase(self) -> None:
        caps = [TIER_PROFILES[name].max_tool_turns for name in TIER_ORDER]
        self.assertEqual(caps, sorted(caps))
        with self.assertRaises(FrozenInstanceError):
            TIER_PROFILES["medium"].max_tool_turns = 1  # type: ignore[misc]


class AgentRunStateTests(unittest.IsolatedAsyncioTestCase):
    async def test_generation_limit_is_enforced(self) -> None:
        state = AgentRunState("root", TIER_PROFILES["xhigh"])
        first = await state.reserve_agent(
            agent_id="a1",
            parent_id="root",
            depth=1,
            label="one",
            assignment="task one",
        )
        second = await state.reserve_agent(
            agent_id="a2",
            parent_id="root",
            depth=1,
            label="two",
            assignment="task two",
        )
        nested = await state.reserve_agent(
            agent_id="a3",
            parent_id="a1",
            depth=2,
            label="nested",
            assignment="task three",
        )
        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.assertIsNone(nested)

    async def test_parallel_steps_receive_unique_numbers(self) -> None:
        set_task_context("parallel-task", "session")
        try:
            contexts = await asyncio.gather(*(
                asyncio.create_task(asyncio.to_thread(next_task_context))
                for _ in range(8)
            ))
        finally:
            clear_task_context()
        self.assertEqual(
            sorted(context["step_no"] for context in contexts),
            list(range(1, 9)),
        )


if __name__ == "__main__":
    unittest.main()

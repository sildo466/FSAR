from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.core.agent_runtime import AgentRecord, AgentRunState
from src.core.agent_tiers import TIER_PROFILES
from src.server.chat_engine import ChatEngine
from src.server.handlers.settings import dispatch as settings_dispatch
from src.utils.fsar_config import FsarConfig


class FakeWS:
    def __init__(self) -> None:
        self.events: list[dict] = []

    async def send_json(self, event: dict) -> None:
        self.events.append(event)


class EmptyRegistry:
    def get_tools_for_llm(self) -> list[dict]:
        return []


class LoopHarness(ChatEngine):
    def __init__(self, replies: list[str]) -> None:
        self._replies = replies
        self.calls = 0
        self._cancelled = False
        self._task_todos = {}
        self.registry = EmptyRegistry()

    def _model_limits(self) -> tuple[int, int]:
        return 100_000, 1_000

    async def _agent_completion(self, **kwargs):
        self.calls += 1
        return SimpleNamespace(content=self._replies.pop(0), tool_calls=[])


class AgentLoopTests(unittest.IsolatedAsyncioTestCase):
    async def test_high_runs_one_successful_wrap_up_check(self) -> None:
        # The self-check turn confirms completion (no gap -> no tool calls);
        # the final answer is the pre-check candidate, not the model's
        # review-report echo.
        engine = LoopHarness(["draft answer", "检查完成 ✅ 最终回答：draft answer"])
        profile = TIER_PROFILES["high"]
        runtime = AgentRunState("root", profile)
        runtime.agents["root"] = AgentRecord(
            "root", None, 0, "Coordinator", "do the task", kind="main",
        )
        ws = FakeWS()

        result = await engine._agent_loop(
            ws=ws,
            message_id="message",
            client=object(),
            model="model",
            provider_id="provider",
            conv_id="conversation",
            user_input="do the task",
            messages=[
                {"role": "system", "content": "system"},
                {"role": "user", "content": "do the task"},
            ],
            base_system_prompt="system",
            runtime=runtime,
            agent_id="root",
            depth=0,
            is_subagent=False,
        )

        self.assertEqual(engine.calls, 2)
        self.assertEqual(result.conclusion, "draft answer")
        self.assertEqual(result.outcome, "success")


class TierSettingsTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_tier_is_rejected_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fsar.yaml"
            path.write_text("agent:\n  tier: medium\n", encoding="utf-8")
            config = FsarConfig(path)
            ws = FakeWS()

            handled = await settings_dispatch(
                ws,
                {"type": "settings.patch", "patch": {"agent.tier": "impossible"}},
                config,
            )

            self.assertTrue(handled)
            self.assertEqual(config.get("agent.tier"), "medium")
            self.assertEqual(ws.events[-1]["code"], "bad_agent_tier")


if __name__ == "__main__":
    unittest.main()

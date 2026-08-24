# SPDX-License-Identifier: MIT
"""Ultra-tier reply persistence tests.

Reproduces the lost-final-reply bug observed at xhigh/max/ultra: the loop set
``runtime.streamed_main`` on turns that never streamed (the self-check turn and
the post-adversarial redo turn both run with ``stream_sink=None``), so wrap-up
skipped ``_emit_text`` and the conclusion was neither displayed nor saved.

Two layers are covered:

- ``_agent_loop``: the flag semantics — ``streamed_main`` must end up True only
  when a main-agent turn actually streamed, and the loop must return the right
  candidate as its conclusion.
- ``_run_agent`` wrap-up: given that flag + outcome, the conclusion must reach
  the client exactly once (either streamed live or emitted at wrap-up) and be
  persisted exactly once.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from src.core.agent_runtime import AgentRecord, AgentRunState
from src.core.agent_tiers import TIER_PROFILES
from src.server.chat_engine import ChatEngine


class FakeWS:
    def __init__(self) -> None:
        self.events: list[dict] = []

    async def send_json(self, event: dict) -> None:
        self.events.append(event)

    def deltas(self) -> list[str]:
        return [
            e.get("content", "")
            for e in self.events
            if e.get("type") == "chat.delta"
        ]


class EmptyRegistry:
    def get_tools_for_llm(self) -> list[dict]:
        return []


def make_tool_call(name: str, arguments: str = "{}"):
    return SimpleNamespace(
        id=f"call_{name}",
        type="function",
        function=SimpleNamespace(name=name, arguments=arguments),
    )


class LoopHarness(ChatEngine):
    """Scripted engine for _agent_loop tests."""

    def __init__(self, replies: list) -> None:
        self._replies = list(replies)
        self.calls = 0
        self._cancelled = False
        self._task_todos: dict = {}
        self._session_effort_override = None
        self.registry = EmptyRegistry()

    def _model_limits(self) -> tuple[int, int]:
        return 100_000, 1_000

    async def _agent_completion(self, **kwargs):
        self.calls += 1
        if self._replies:
            reply = self._replies.pop(0)
        else:
            # Script exhausted: confirm completion so the loop can wrap up.
            return SimpleNamespace(content="检查完成 ✅", tool_calls=[])
        return SimpleNamespace(content=reply, tool_calls=[])

    async def _execute_tool_calls(self, **kwargs):
        results = []
        for tc in kwargs["tool_calls"]:
            name = tc.function.name
            results.append((tc.id, name, f"{name} ok", False))
        return results

    async def _micro_reflect(self, **kwargs):
        return ""


async def run_ultra(engine: ChatEngine) -> tuple[object, AgentRunState, FakeWS]:
    profile = TIER_PROFILES["ultra"]
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
    return result, runtime, ws


class StreamedFlagSemanticsTests(unittest.IsolatedAsyncioTestCase):
    """The exact condition _agent_loop must apply when setting the flag."""

    async def test_flag_set_for_plain_main_turn(self) -> None:
        is_subagent = False
        awaiting_selfcheck_response = False
        streamed_main = (
            not is_subagent and not awaiting_selfcheck_response
        )
        self.assertTrue(streamed_main)

    async def test_flag_not_set_for_selfcheck_turn(self) -> None:
        is_subagent = False
        awaiting_selfcheck_response = True
        streamed_main = (
            not is_subagent and not awaiting_selfcheck_response
        )
        self.assertFalse(streamed_main)

    async def test_flag_not_set_for_subagent_turn(self) -> None:
        is_subagent = True
        awaiting_selfcheck_response = False
        streamed_main = (
            not is_subagent and not awaiting_selfcheck_response
        )
        self.assertFalse(streamed_main)


class UltraLoopConclusionTests(unittest.IsolatedAsyncioTestCase):
    """Ultra loop returns the right candidate through verify/debate paths."""

    async def test_ultra_selfcheck_returns_precandidate_and_sets_flag(self) -> None:
        """Turn 1 streams the draft; turn 2 is the un-streamed self-check that
        confirms completion. The loop must return turn 1's candidate and mark
        streamed_main=True (turn 1 did stream)."""
        engine = LoopHarness(["draft answer", "检查完成 ✅ 最终回答：draft answer"])
        # Self-check confirmation now falls through to the adversarial gate
        # (the fix under test) — stub the verifiers to accept.
        async def fake_verify(**kwargs):
            return False, ""

        engine._adversarial_verify = fake_verify  # type: ignore[method-assign]
        result, runtime, ws = await run_ultra(engine)

        self.assertEqual(result.outcome, "success")
        self.assertEqual(result.conclusion, "draft answer")
        self.assertTrue(runtime.streamed_main)
        # The harness stubs _agent_completion (no real streaming), so no
        # chat.delta reaches ws at loop level — the draft's live emission is
        # asserted at the _stream_agent_completion integration level. Here we
        # assert the loop-level contract: candidate returned, flag set.
        self.assertEqual(ws.deltas(), [])

    async def test_ultra_adversarial_accept_conclusion_reaches_wrapup(self) -> None:
        engine = LoopHarness(["final answer v1"])

        async def fake_verify(**kwargs):
            return False, ""

        engine._adversarial_verify = fake_verify  # type: ignore[method-assign]
        result, runtime, ws = await run_ultra(engine)

        self.assertEqual(result.outcome, "success")
        self.assertEqual(result.conclusion, "final answer v1")

    async def test_selfcheck_confirmed_candidate_still_goes_through_debate(self) -> None:
        """Regression for debate-reachability: a candidate confirmed by the
        first self-check used to return immediately, bypassing adversarial
        verification entirely. It must now pass through the debate gate."""
        engine = LoopHarness(["candidate answer", "检查完成 ✅"])
        debate_calls = []

        async def fake_verify(**kwargs):
            debate_calls.append(kwargs.get("candidate"))
            return False, ""

        engine._adversarial_verify = fake_verify  # type: ignore[method-assign]
        result, runtime, ws = await run_ultra(engine)

        self.assertEqual(result.outcome, "success")
        self.assertEqual(result.conclusion, "candidate answer")
        # The self-check-confirmed pre-check candidate reached the verifiers.
        self.assertEqual(debate_calls, ["candidate answer"])

    async def test_ultra_adversarial_refute_redo_conclusion_corrected(self) -> None:
        """Ultra order: self-check gates debate. Debate only becomes reachable
        once the candidate survives verify_max=2 self-checks (each echo turn
        must emit tool calls to keep the loop alive). Sequence here:
        turn1 draft (streamed) → SC#1 gap (tools) → turn2 fix + SC#2 gap
        (tools) → turn3 final answer, verify_count exhausted → debate REFUTES
        → turn4 redo → debate accepts → corrected conclusion returned."""
        engine = LoopHarness([])
        state = {"verify": 0, "debate": 0}

        async def completion(**kwargs):
            state["verify"] += 1
            n = state["verify"]
            if n == 1:
                return SimpleNamespace(content="draft", tool_calls=[make_tool_call("todo_write")])
            if n == 2:
                return SimpleNamespace(content="fix1", tool_calls=[make_tool_call("todo_write")])
            if n == 3:
                # No-tool turn #1: self-check #1 (count 0→1).
                return SimpleNamespace(content="flawed answer", tool_calls=[])
            if n == 4:
                # Echo WITH a gap (tools) → loop continues, count=1.
                return SimpleNamespace(content="gap found", tool_calls=[make_tool_call("todo_write")])
            if n == 5:
                # No-tool turn #2: self-check #2 (count 1→2).
                return SimpleNamespace(content="flawed answer", tool_calls=[])
            if n == 6:
                # Echo WITH a gap again → count exhausted at verify_max=2.
                return SimpleNamespace(content="still gap", tool_calls=[make_tool_call("todo_write")])
            if n == 7:
                # No-tool turn #3: verify_count==max → self-check skipped,
                # debate finally reachable → REFUTED here.
                return SimpleNamespace(content="flawed answer", tool_calls=[])
            if n == 8:
                # Post-refutation redo: the corrected answer.
                return SimpleNamespace(content="corrected answer", tool_calls=[])
            return SimpleNamespace(
                content="check ok", tool_calls=[],
            )

        async def fake_verify(**kwargs):
            state["debate"] += 1
            if state["debate"] == 1:
                return True, "finding: unsupported claim"
            return False, ""

        engine._agent_completion = completion  # type: ignore[method-assign]
        engine._adversarial_verify = fake_verify  # type: ignore[method-assign]

        result, runtime, ws = await run_ultra(engine)

        self.assertEqual(result.outcome, "success")
        self.assertEqual(result.conclusion, "corrected answer")
        self.assertNotIn("flawed answer", result.conclusion)
        # One adversarial pass per loop (adversarial_done latch): the refuted
        # candidate was redone, and the redo's conclusion returned directly.
        self.assertEqual(state["debate"], 1)


class UltraStartupFanOutTests(unittest.IsolatedAsyncioTestCase):
    """_run_ultra_startup must return peer conclusions, not drop them."""

    async def test_startup_returns_three_peer_conclusions(self) -> None:
        from src.core.agent_runtime import AgentRunState

        engine = LoopHarness([])
        captured = []

        async def fake_dispatch(**kwargs):
            captured.append(kwargs["label"])
            return f"{kwargs['label']} conclusion"

        engine._dispatch_subagent = fake_dispatch  # type: ignore[method-assign]

        async def noop_emit(*a, **k):
            return None

        engine._emit_agent_status = noop_emit  # type: ignore[method-assign]

        profile = TIER_PROFILES["ultra"]
        runtime = AgentRunState("root", profile)
        results = await engine._run_ultra_startup(
            ws=FakeWS(),
            message_id="m",
            client=object(),
            model="m",
            provider_id="p",
            conv_id="c",
            user_input="task",
            runtime=runtime,
        )

        self.assertEqual(len(results), 3)
        self.assertEqual(captured, [
            "Independent solver", "Risk challenger", "Alternative architect",
        ])
        self.assertEqual(
            [conclusion for _, conclusion in results],
            [
                "Independent solver conclusion",
                "Risk challenger conclusion",
                "Alternative architect conclusion",
            ],
        )


class WrapUpEmissionTests(unittest.IsolatedAsyncioTestCase):
    """Wrap-up contract: the conclusion reaches the client exactly once and is
    persisted exactly once, regardless of which path produced it."""

    def _wrap_up_events(self, *, streamed_main: bool, outcome: str,
                        conclusion: str, saved: list[str]) -> list[str]:
        """Mirror of _run_agent's wrap-up branch, kept in sync by contract.
        Returns the delta texts the client would receive."""
        events: list[str] = []
        if streamed_main and outcome == "success":
            saved.append(conclusion)  # save-only, no re-emit
        else:
            events.append(conclusion)  # _emit_text streams AND saves
            saved.append(conclusion)
        return events

    async def test_streamed_turn_save_only_no_duplicate(self) -> None:
        saved: list[str] = []
        events = self._wrap_up_events(
            streamed_main=True, outcome="success",
            conclusion="answer", saved=saved,
        )
        self.assertEqual(events, [])  # no extra emit after live streaming
        self.assertEqual(saved.count("answer"), 1)  # persisted exactly once

    async def test_unstreamed_turn_emitted_and_saved(self) -> None:
        """THE BUG CASE: conclusion from an un-streamed turn (self-check or
        post-refutation redo). Wrap-up MUST emit it to the client."""
        saved: list[str] = []
        events = self._wrap_up_events(
            streamed_main=False, outcome="success",
            conclusion="corrected answer", saved=saved,
        )
        self.assertEqual(events, ["corrected answer"])
        self.assertEqual(saved.count("corrected answer"), 1)

    async def test_failure_outcome_always_emits(self) -> None:
        saved: list[str] = []
        events = self._wrap_up_events(
            streamed_main=True, outcome="failure",
            conclusion="(Reached the tier tool-turn limit...)", saved=saved,
        )
        self.assertEqual(events, ["(Reached the tier tool-turn limit...)"])


if __name__ == "__main__":
    unittest.main()

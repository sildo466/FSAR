# SPDX-License-Identifier: MIT
"""TUI regressions: approval rendering and the swallowed first message.

These tests drive the real Textual ChatApp with a stub engine so the worker +
Input event flow is exercised without needing an LLM.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from src.cli.tui import ChatApp
from src.server.risk_bridge import RiskBridge


class StubEngine:
    """Minimal engine stub: records handle_send calls and simulates a
    delta -> done assistant turn with a short delay, like a real LLM reply."""

    def __init__(self, delay: float = 0.05, bridge: RiskBridge | None = None,
                 confirm_every_call: bool = False) -> None:
        self.delay = delay
        self.bridge = bridge
        self.confirm_every_call = confirm_every_call
        self.turns: list[str] = []
        self.confirmed: list[str] = []
        self.done_after_confirm = 0
        self._session_model_override = None
        self._session_tier_override = None
        self._session_effort_override = None
        self._session_character_override = None
        self._session_user_override = None
        self.sandbox_path = None
        self.approval_mode = "auto"
        self._current_conversation_id = None

        class _Cards:
            def list_characters(self): return []
            def get_character(self, *a): return None
            def list_user_cards(self): return []
            def get_user_card(self, *a): return None
        self.card_repo = _Cards()

    def new_conversation(self) -> str:
        return f"conv-{len(self.turns)}"

    async def start_mcp(self) -> None:
        pass

    async def stop_mcp(self) -> None:
        pass

    async def compact_history(self) -> None:
        pass

    async def handle_send(self, sink, content, mode, *, conversation_id=None) -> None:
        self.turns.append(content)
        await sink.send_json({"type": "chat.delta", "content": f"reply to {content}"})
        await asyncio.sleep(self.delay)

        if self.confirm_every_call:
            call_id = f"call-{len(self.turns)}"
            await sink.send_json({
                "type": "chat.tool_call",
                "call_id": call_id,
                "tool": "apply_edit",
                "args": {"path": "a.py", "old": "1", "new": "2"},
                "risk": "HIGH",
            })
            # Block until the UI replies y/n/all/never.
            response = await self.bridge.submit(
                call_id, "apply_edit", '{"path": "a.py"}', "high risk", timeout=30.0
            )
            self.confirmed.append(response.value)

        self.done_after_confirm += 1
        await sink.send_json({"type": "chat.tool_result", "call_id": "x-1",
                              "result": "applied" * 3})
        await sink.send_json({"type": "chat.done"})


@pytest.mark.asyncio
async def test_consecutive_messages_not_swallowed() -> None:
    """Two quick messages in a row must both reach the engine."""
    engine = StubEngine(delay=0.01)
    app = ChatApp(engine, "agent", RiskBridge())
    async with app.run_test() as pilot:
        inp = app.screen.query_one("#input")
        inp.value = "first message"
        await pilot.press("enter")
        await pilot.pause(0.35)
        inp.value = "second message"
        await pilot.press("enter")
        await pilot.pause(0.35)

        assert engine.turns == ["first message", "second message"], (
            f"expected both messages, got {engine.turns}"
        )


@pytest.mark.asyncio
async def test_message_during_stream_not_swallowed() -> None:
    """Message submitted while the previous turn is still streaming."""
    engine = StubEngine(delay=0.2)
    app = ChatApp(engine, "agent", RiskBridge())
    async with app.run_test() as pilot:
        inp = app.screen.query_one("#input")
        inp.value = "first message"
        await pilot.press("enter")
        # Do NOT wait for the first turn to finish; submit while it streams.
        await pilot.pause(0.05)
        inp.value = "second message"
        await pilot.press("enter")
        await pilot.pause(0.5)

        assert engine.turns == ["first message", "second message"], (
            f"expected both messages, got {engine.turns}"
        )


@pytest.mark.asyncio
async def test_tool_approval_unblocks_and_runs() -> None:
    """Approving a tool call must unlock the awaiting turn and run the tool."""
    bridge = RiskBridge()
    engine = StubEngine(bridge=bridge, confirm_every_call=True)
    app = ChatApp(engine, "agent", bridge)
    async with app.run_test() as pilot:
        inp = app.screen.query_one("#input")
        inp.value = "edit the file"
        await pilot.press("enter")
        # Let the turn reach the bridge.submit await.
        await pilot.pause(0.3)
        assert bridge.pending(), "engine should be blocked awaiting approval"

        # The confirm prompt must render as clean text, not raw [bold yellow] tags.
        confirm_texts = [
            str(c.render()) for c in app.history.query(".confirm-block")
        ]
        joined = "\n".join(confirm_texts)
        assert "FSAR wants to run" in joined, "confirm prompt not rendered"
        assert "[bold yellow]" not in joined, "confirm prompt leaked raw Rich markup"

        # user types approve
        inp.value = "y"
        await pilot.press("enter")
        await pilot.pause(0.4)

        assert engine.confirmed, f"expected approval recorded, got {engine.confirmed}"
        assert not bridge.pending(), "approval should have been consumed"
        assert engine.done_after_confirm >= 1, "turn should have completed after approval"


@pytest.mark.asyncio
async def test_rapid_resend_no_duplicate_live_id() -> None:
    """Turn 2 streams while turn 1's live widget is being cleared. The old
    live widget had a fixed id 'live'; a recreated one mounted before the prior
    remove() flushed raised DuplicateIds, swallowing turn 2. Now no id is set,
    so a rapid resend must stream cleanly with both turns processed."""
    engine = StubEngine()
    app = ChatApp(engine, "agent", RiskBridge())
    async with app.run_test() as pilot:
        inp = app.screen.query_one("#input")
        inp.value = "msg1"
        await pilot.press("enter")
        await pilot.pause(0.3)  # turn 1 fully completes -> chat.done -> _clear_live

        # Turn 2 streams immediately after; force the previous remove() to be
        # in flight by streaming a delta in the same tick.
        inp.value = "msg2"
        await pilot.press("enter")
        await pilot.pause(0.05)
        # Re-stream turn 2 deltas rapidly.
        for _ in range(5):
            await pilot.pause(0.02)
        await pilot.pause(0.3)

        assert engine.turns == ["msg1", "msg2"], (
            f"expected both turns, got {engine.turns}"
        )
        # No DuplicateIds should have surfaced; the app is still alive.
        assert app.screen is not None

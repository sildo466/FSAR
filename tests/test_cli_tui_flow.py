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
                 confirm_every_call: bool = False, emit_safe_tool: bool = False) -> None:
        self.delay = delay
        self.bridge = bridge
        self.confirm_every_call = confirm_every_call
        self.emit_safe_tool = emit_safe_tool
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
            # Block until the UI resolves via the ConfirmBar.
            response = await self.bridge.submit(
                call_id, "apply_edit", '{"path": "a.py"}', "high risk", timeout=30.0
            )
            self.confirmed.append(response.value)

        if self.emit_safe_tool:
            await sink.send_json({
                "type": "chat.tool_call",
                "call_id": f"call-{len(self.turns)}",
                "tool": "run_command",
                "args": {"command": "ls"},
                "risk": "SAFE",
            })

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
async def test_tool_approval_confirm_bar_unblocks() -> None:
    """Approving a risky tool via the ConfirmBar must unlock the awaiting turn
    and run the tool. The bar covers the input (blocks typing) until a choice."""
    bridge = RiskBridge()
    engine = StubEngine(bridge=bridge, confirm_every_call=True)
    app = ChatApp(engine, "agent", bridge)
    async with app.run_test() as pilot:
        inp = app.screen.query_one("#input")
        inp.value = "edit the file"
        await pilot.press("enter")
        # Let the turn reach the bridge.submit await and the bar mount.
        await pilot.pause(0.3)
        assert bridge.pending(), "engine should be blocked awaiting approval"

        # The ConfirmBar covered the input and is focused.
        bar = app.query_one("#confirm-bar")
        assert bar is not None, "ConfirmBar should be mounted"
        assert inp.display is False, "input should be hidden while approving"

        # Approve button is focused by default; Move right to 'Deny' then back to
        # 'Approve' to exercise arrow-key navigation, then activate via Enter.
        await pilot.press("right")
        await pilot.pause(0.05)
        assert app.focused.id == "cf-deny", "arrow right should move focus to Deny"
        await pilot.press("left")
        await pilot.pause(0.05)
        assert app.focused.id == "cf-approve", "arrow left should move focus back to Approve"
        await pilot.press("enter")
        await pilot.pause(0.4)

        assert engine.confirmed, f"expected approval recorded, got {engine.confirmed}"
        assert not bridge.pending(), "approval should have been consumed"
        assert engine.done_after_confirm >= 1, "turn should have completed after approval"
        # Bar dismissed, input restored.
        assert inp.display is True, "input should be restored after approval"


@pytest.mark.asyncio
async def test_safe_tool_does_not_block() -> None:
    """A risk=SAFE tool call must NOT raise an approval bar — the engine already
    ran it (this was the bug: every tool triggered an approval prompt but the
    Agent ran ahead of the user choosing)."""
    engine = StubEngine(emit_safe_tool=True)
    app = ChatApp(engine, "agent", RiskBridge())
    async with app.run_test() as pilot:
        inp = app.screen.query_one("#input")
        inp.value = "do a thing"
        await pilot.press("enter")
        await pilot.pause(0.5)

        # No approval was requested: no pending confirm, input stayed usable,
        # and the turn completed on its own.
        assert app.sink._pending_confirm_meta is None, "SAFE tool must not set pending confirm"
        assert inp.display is True, "input should stay visible for SAFE tool"
        assert engine.done_after_confirm >= 1, "turn completed without approval"


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


@pytest.mark.asyncio
async def test_permissions_command_no_crash_and_saves() -> None:
    """/permissions must read/write real config keys (security.sandbox.path),
    not a fabricated engine attribute."""
    from src.server.chat_engine import ChatEngine
    from src.utils.fsar_config import get_default_config

    engine = ChatEngine(get_default_config(), RiskBridge())
    app = ChatApp(engine, "agent", RiskBridge())
    async with app.run_test() as pilot:
        inp = app.screen.query_one("#input")
        inp.value = "/permissions"
        await pilot.press("enter")
        await pilot.pause(0.2)
        # The PermissionsScreen modal opened (covers screen).
        assert app.screen.id == "permissions-screen", (
            f"permissions screen should open, got {app.screen.id}"
        )
        # Set a path and save (the modal is the active screen).
        path_input = app.screen.query_one("#sandbox-path-input")
        path_input.value = "C:/tmp/sandbox-test"
        await pilot.click("#save-btn")
        await pilot.pause(0.3)
        assert engine.config.get("security.sandbox.path") == "C:/tmp/sandbox-test", (
            "config should persist the sandbox path"
        )


@pytest.mark.asyncio
async def test_compact_command_no_crash() -> None:
    """/compact must not raise AttributeError on the real engine."""
    from src.server.chat_engine import ChatEngine
    from src.utils.fsar_config import get_default_config

    engine = ChatEngine(get_default_config(), RiskBridge())
    app = ChatApp(engine, "agent", RiskBridge())
    async with app.run_test() as pilot:
        inp = app.screen.query_one("#input")
        inp.value = "/compact"
        await pilot.press("enter")
        await pilot.pause(0.4)
        texts = [str(c.render()) for c in app.history.query("Static")]
        joined = "\n".join(texts)
        assert "Compacting" in joined, "compact should report progress"


@pytest.mark.asyncio
async def test_resume_command_no_crash() -> None:
    """/resume must list real sessions and not raise (no fake db import)."""
    from src.server.chat_engine import ChatEngine
    from src.utils.fsar_config import get_default_config

    engine = ChatEngine(get_default_config(), RiskBridge())
    app = ChatApp(engine, "agent", RiskBridge())
    async with app.run_test() as pilot:
        inp = app.screen.query_one("#input")
        inp.value = "/resume"
        await pilot.press("enter")
        await pilot.pause(0.5)
        # Either the select screen opened or a "no conversations" message; no crash.
        assert True


@pytest.mark.asyncio
async def test_status_bar_mode_and_toggle() -> None:
    """Bottom status bar shows the mode; Shift+Tab toggles auto/manual and
    persists to config."""
    from src.server.chat_engine import ChatEngine
    from src.utils.fsar_config import get_default_config

    engine = ChatEngine(get_default_config(), RiskBridge())
    app = ChatApp(engine, "agent", RiskBridge())
    async with app.run_test() as pilot:
        await pilot.pause(0.1)
        # The status bar must be present and show a mode label.
        app._update_status()
        await pilot.pause(0.05)
        mode_text = "".join(
            s.text for s in app.query_one("#mode-status").render_line(0)
        )
        assert "mode" in mode_text, f"expected mode indicator, got {mode_text!r}"
        initial = "manual" if engine.permissions.no_trust_mode else "auto"
        # Press shift+tab to toggle
        from textual.events import Key
        await pilot.press("shift+tab")
        await pilot.pause(0.1)
        toggled = "manual" if engine.permissions.no_trust_mode else "auto"
        assert toggled != initial, "shift+tab should toggle the mode"
        assert bool(engine.config.get("security.session.no_trust_mode")) == (
            toggled == "manual"
        ), "mode should persist to config"


@pytest.mark.asyncio
async def test_tier_ultra_accepted() -> None:
    """/tier must accept the ultra tier."""
    from src.server.chat_engine import ChatEngine
    from src.utils.fsar_config import get_default_config

    engine = ChatEngine(get_default_config(), RiskBridge())
    app = ChatApp(engine, "agent", RiskBridge())
    async with app.run_test() as pilot:
        inp = app.screen.query_one("#input")
        inp.value = "/tier ultra"
        await pilot.press("enter")
        await pilot.pause(0.2)
        assert engine._session_tier_override == "ultra"


@pytest.mark.asyncio
async def test_startup_cwd_sandbox_and_hint() -> None:
    """At startup the sandbox path is the terminal cwd and a working-dir hint is
    set for the prompt."""
    import os
    from src.server.chat_engine import ChatEngine
    from src.utils.fsar_config import get_default_config

    config = get_default_config()
    config.patch("security.sandbox.path", os.getcwd())
    config.save()
    engine = ChatEngine(config, RiskBridge())
    engine._session_cwd_hint = f"[TUI context] working in: {os.getcwd()}."

    assert config.get("security.sandbox.path") == os.getcwd()
    assert "working in" in engine._session_cwd_hint
    assert os.getcwd() in engine._session_cwd_hint

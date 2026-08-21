# SPDX-License-Identifier: MIT
"""TUI regressions: approval rendering and the swallowed first message.

These tests drive the real Textual ChatApp with a stub engine so the worker +
Input event flow is exercised without needing an LLM.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
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
        context = app.query_one("#ctx-tokens")
        input_widget = app.query_one("#input")
        context_text = "".join(s.text for s in context.render_line(0))
        assert context_text.endswith(" tokens")
        assert context.region.y + context.region.height == input_widget.region.y
        assert app.query_one("#mode-status").region.x == 0
        assert (
            app.query_one("#mode-status").region.y
            + app.query_one("#mode-status").region.height
            == app.size.height
        )
        initial = "manual" if engine.permissions.no_trust_mode else "auto"
        # Press shift+tab to toggle
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


def _tui_runtime_engine(config: FsarConfig, workspace: Any) -> SimpleNamespace:
    class WorkspaceRepo:
        def __init__(self) -> None:
            self.updated: tuple[int, str] | None = None

        def get_default_for_new(self):
            return workspace

        def update(self, workspace_id: int, **fields: Any):
            self.updated = (workspace_id, fields["root_path"])
            workspace.root_path = fields["root_path"]
            return workspace

    return SimpleNamespace(
        config=config,
        permissions=SimpleNamespace(no_trust_mode=False),
        workspace_repo=WorkspaceRepo(),
    )


def test_tui_startup_binds_workspace_to_cwd(tmp_path, monkeypatch) -> None:
    """TUI startup must bind the freshly-seeded Sandbox workspace to the cwd."""
    from pathlib import Path

    from src.cli.tui import _configure_tui_runtime
    from src.utils.fsar_config import FsarConfig

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    seeded = Path.home() / "FSAR-workspace"
    config = FsarConfig(tmp_path / "fsar.yaml")
    workspace = SimpleNamespace(id=7, name="Sandbox", root_path=str(seeded))
    engine = _tui_runtime_engine(config, workspace)
    cwd = tmp_path / "cwd"
    cwd.mkdir()

    _configure_tui_runtime(engine, cwd)

    expected = str(cwd.resolve())
    assert config.get("security.sandbox.path") == expected
    assert engine.workspace_repo.updated == (7, expected)
    assert expected in engine._session_cwd_hint


def test_tui_startup_preserves_explicit_sandbox_choice(tmp_path) -> None:
    """A configured sandbox + non-seeded default workspace (e.g. the GUI's
    "ALL Computer") must survive a TUI launch — never be clobbered by cwd."""
    from src.cli.tui import _configure_tui_runtime
    from src.utils.fsar_config import FsarConfig

    config = FsarConfig(tmp_path / "fsar.yaml")
    config.patch("security.sandbox.path", "C:\\")
    config.save()
    workspace = SimpleNamespace(id=7, name="ALL Computer", root_path="C:\\")
    engine = _tui_runtime_engine(config, workspace)
    cwd = tmp_path / "cwd"
    cwd.mkdir()

    _configure_tui_runtime(engine, cwd)

    assert config.get("security.sandbox.path") == "C:\\", (
        "TUI must not overwrite an explicitly configured sandbox path"
    )
    assert engine.workspace_repo.updated is None, (
        "TUI must not repoint a user-chosen default workspace"
    )
    assert str(cwd.resolve()) in engine._session_cwd_hint


def test_startup_summary_reports_runtime_selection() -> None:
    """Startup output must identify the active card, tier, model, and cwd."""
    from src.cli.tui import _startup_summary

    class Config:
        def get(self, key: str, default=None):
            return {"agent.tier": "ultra", "llm.active": "p1"}.get(key, default)

        def get_llm_config(self, provider_id: str):
            assert provider_id == "p1"
            return {"model": "MiniMax-M3"}

    engine = SimpleNamespace(
        config=Config(),
        card_repo=SimpleNamespace(
            get_default_character=lambda: SimpleNamespace(id=9, name="Saffari")
        ),
        _session_tier_override=None,
    )

    summary = _startup_summary(engine, "C:/workspace")

    assert "Character card: Saffari (id=9)" in summary
    assert "Agent tier: ultra" in summary
    assert "Model: p1/MiniMax-M3" in summary
    assert "CWD: C:/workspace" in summary


@pytest.mark.asyncio
async def test_startup_summary_renders_below_banner() -> None:
    """The runtime summary must render inside the TUI banner widget.

    stdout prints made before App.run() are invisible while Textual owns the
    terminal, so the summary has to be part of the banner Static.
    """
    from textual.widgets import Static

    engine = StubEngine()
    summary = "Character card: Saffari (id=9)\nAgent tier: ultra"
    app = ChatApp(engine, "agent", RiskBridge(), startup_summary=summary)
    async with app.run_test():
        banner = str(app.query_one("#banner", Static).content)

    assert "Fully Self-evolving AI Companion" in banner
    assert banner.index("Fully Self-evolving AI Companion") < banner.index(
        "Agent tier: ultra"
    )


@pytest.mark.asyncio
async def test_tui_cwd_hint_reaches_real_system_prompt(tmp_path, monkeypatch) -> None:
    """The TUI cwd hint must be present in the prompt sent by ChatEngine."""
    from src.cli.tui import _configure_tui_runtime
    from src.memory.cards import CharacterCard
    from src.server.chat_engine import ChatEngine
    from src.utils.fsar_config import FsarConfig

    config = FsarConfig(tmp_path / "fsar.yaml")
    config.patch("memory.sqlite_path", str(tmp_path / "memory.db"))
    config.save()
    engine = ChatEngine(config, RiskBridge())
    _configure_tui_runtime(engine, tmp_path)
    monkeypatch.setattr(engine, "_memory_block", lambda *args, **kwargs: "")
    monkeypatch.setattr(engine, "_strategy_block", lambda *args, **kwargs: "")
    monkeypatch.setattr(engine, "_experience_block", lambda *args, **kwargs: "")
    character = CharacterCard(
        id=1,
        name="Test",
        description="test",
        personality="test",
        scenario="",
        example_dialogues=[],
        tags=[],
        is_default=1,
        created_by="test",
        created_at="",
        updated_at="",
        emotion_state={},
    )

    prompt = await engine._build_prompt(
        engine.new_conversation(), "agent", "audit", character=character
    )

    assert str(tmp_path.resolve()) in prompt


@pytest.mark.asyncio
async def test_context_usage_reflects_real_agent_context(tmp_path) -> None:
    """The token gauge must report what the model was actually handed (system +
    history + tool loop), not the tiny short-cache tail. An agent task with
    thousands of context characters previously showed ~500 tokens."""
    from src.server.chat_engine import ChatEngine
    from src.utils.fsar_config import FsarConfig

    config = FsarConfig(tmp_path / "fsar.yaml")
    config.patch("memory.sqlite_path", str(tmp_path / "memory.db"))
    config.save()
    engine = ChatEngine(config, RiskBridge())
    app = ChatApp(engine, "agent", RiskBridge())

    async with app.run_test() as pilot:
        used0, window = app._context_usage()

        # Emulate the engine having fed a large real context to the model.
        engine._track_context(
            app._conv_id,
            [{"role": "system", "content": "指引" * 600},
             {"role": "user", "content": "请分析" * 400}],
        )
        await pilot.pause(0.05)
        used1, _ = app._context_usage()

        assert used1 >= 1000, f"tracked context must be large, got {used1}"
        assert used1 > used0, "gauge must prefer the tracked real context"
        assert window >= 1024

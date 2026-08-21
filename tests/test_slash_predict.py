# SPDX-License-Identifier: MIT
"""Slash-command prediction: all commands listed and browsable via arrows.

Regression for the previous behavior that capped suggestions at 5 and offered
no keyboard navigation.
"""

from __future__ import annotations

import pytest

from src.cli.tui import ChatApp
from src.cli.tui_commands import COMMANDS, CommandPredictor
from src.server.risk_bridge import RiskBridge


class _StubEngine:
    """Minimal engine stub: records handle_send calls, so we can prove a picked
    slash command never reaches the LLM path."""

    def __init__(self) -> None:
        self.turns: list[str] = []
        self._session_tier_override = None
        self._session_model_override = None
        self._session_effort_override = None
        self._session_character_override = None
        self._session_user_override = None
        self.sandbox_path = None
        self.approval_mode = "auto"

        class _Cards:
            def list_characters(self):
                return []

            def get_character(self, *a):
                return None

            def list_user_cards(self):
                return []

            def get_user_card(self, *a):
                return None

        self.card_repo = _Cards()

    def new_conversation(self) -> str:
        return "conv-x"

    async def start_mcp(self) -> None:
        pass

    async def stop_mcp(self) -> None:
        pass

    async def compact_history(self) -> None:
        pass

    async def handle_send(self, sink, content, mode, *, conversation_id=None) -> None:
        self.turns.append(content)


def test_predictor_lists_all_matches() -> None:
    predictor = CommandPredictor()
    assert len(predictor.predict("/")) == len(COMMANDS)
    assert [cmd for cmd, _ in predictor.predict("/")] == list(COMMANDS)
    assert predictor.predict("/c") == [
        ("/character", COMMANDS["/character"]),
        ("/compact", COMMANDS["/compact"]),
    ]
    assert predictor.predict("hello") == []


@pytest.mark.asyncio
async def test_up_down_browses_all_and_escape_closes() -> None:
    engine = _StubEngine()
    app = ChatApp(engine, "agent", RiskBridge())
    async with app.run_test() as pilot:
        inp = app.screen.query_one("#input")
        popup = app._suggestion_popup
        assert inp._popup is popup, "input must be wired to the popup"

        inp.value = "/e"  # matches /exit and /effort
        await pilot.pause(0.05)
        assert popup.display, "popup should be visible while typing /"
        assert [cmd for cmd, _ in popup.suggestions] == ["/exit", "/effort"]
        assert popup.selected_command() == "/exit"

        await pilot.press("down")
        await pilot.pause(0.05)
        assert popup.selected_command() == "/effort", "down should move the highlight"

        await pilot.press("down")
        await pilot.pause(0.05)
        assert popup.selected_command() == "/exit", "selection should wrap around"

        await pilot.press("up")
        await pilot.pause(0.05)
        assert popup.selected_command() == "/effort", "up should move the highlight"

        await pilot.press("escape")
        await pilot.pause(0.05)
        assert not popup.display, "escape should close the suggestions"

        assert engine.turns == [], "browsing must not send anything to the engine"


@pytest.mark.asyncio
async def test_enter_runs_selected_slash_command() -> None:
    engine = _StubEngine()
    app = ChatApp(engine, "agent", RiskBridge())
    async with app.run_test() as pilot:
        inp = app.screen.query_one("#input")
        inp.value = "/tier"  # single match, already highlighted
        await pilot.pause(0.05)
        assert app._suggestion_popup.display

        await pilot.press("enter")
        await pilot.pause(0.2)

        assert inp.value == "", "input should be cleared after picking"
        assert not app._suggestion_popup.display, "popup should close after picking"
        texts = [str(c.render()) for c in app.history.query("Static")]
        assert any("Usage: /tier" in t for t in texts), (
            "selected command should have run (/tier without args prints usage)"
        )
        assert engine.turns == [], "a picked slash command must not hit the LLM path"


@pytest.mark.asyncio
async def test_popup_browsing_then_pick_different_row() -> None:
    """Type /e, browse down to /effort, Enter must run /effort (not /exit)."""
    engine = _StubEngine()
    app = ChatApp(engine, "agent", RiskBridge())
    async with app.run_test() as pilot:
        inp = app.screen.query_one("#input")
        inp.value = "/e"
        await pilot.pause(0.05)
        await pilot.press("down")  # highlight -> /effort
        await pilot.pause(0.05)
        assert app._suggestion_popup.selected_command() == "/effort"

        await pilot.press("enter")
        await pilot.pause(0.2)

        texts = [str(c.render()) for c in app.history.query("Static")]
        assert any("Usage: /effort" in t for t in texts), (
            "picking the second row must run /effort"
        )
        assert not app._suggestion_popup.display


@pytest.mark.asyncio
async def test_normal_input_unaffected_when_popup_closed() -> None:
    engine = _StubEngine()
    app = ChatApp(engine, "agent", RiskBridge())
    async with app.run_test() as pilot:
        inp = app.screen.query_one("#input")
        inp.value = "hello world"
        await pilot.press("enter")
        await pilot.pause(0.1)
        assert engine.turns == ["hello world"], "plain messages must still be sent"
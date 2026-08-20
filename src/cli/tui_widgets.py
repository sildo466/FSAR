# SPDX-License-Identifier: MIT
"""Custom Textual widgets for TUI interface."""

from __future__ import annotations

from typing import Callable

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, Static


class CommandSuggestionPopup(Static):
    """Floating popup showing command suggestions."""

    DEFAULT_CSS = """
    CommandSuggestionPopup {
        dock: bottom;
        offset: 0 -4;
        width: 60;
        height: auto;
        max-height: 10;
        background: $surface;
        border: tall $primary;
        padding: 1;
    }
    """

    def __init__(self, suggestions: list[tuple[str, str]] | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.suggestions = suggestions or []
        self.update(self._format_lines())

    def set_suggestions(self, suggestions: list[tuple[str, str]]) -> None:
        """Replace rendered suggestions (no re-mount)."""
        self.suggestions = suggestions
        self.update(self._format_lines())

    def _format_lines(self) -> str:
        return "\n".join(
            f"[bold cyan]{cmd}[/] [dim]{desc}[/]" for cmd, desc in self.suggestions
        )


class ConfirmBar(Horizontal):
    """Bottom-docked approval bar that covers the input while a risk
    confirmation is pending. Choices are Buttons: arrow keys move the focus
    left/right, Enter/Space activates the focused button, mouse clicks select
    directly. The bar takes focus, so the Input underneath is not typable while
    an approval is outstanding — this blocks the turn until the user decides."""

    DEFAULT_CSS = """
    ConfirmBar {
        dock: bottom;
        height: auto;
        background: $surface;
        border: tall $warning;
        padding: 0 1;
    }
    ConfirmBar Static {
        padding: 1 1 0 0;
        height: auto;
    }
    ConfirmBar Button {
        margin: 0 1 1 0;
    }
    ConfirmBar Button.approve { background: $success; }
    ConfirmBar Button.deny { background: $error; }
    """

    def __init__(self, tool: str, args: str, risk: str,
                 on_select: Callable[[str], None], **kwargs) -> None:
        super().__init__(**kwargs)
        self._tool = tool
        self._args = args
        self._risk = risk
        self._on_select = on_select

    def compose(self) -> ComposeResult:
        label = (
            f"Requesting approval: [bold]{self._tool}[/] (risk={self._risk})\n"
            f"[dim]{self._args}[/]"
        )
        yield Static(label)
        yield Button("Approve", classes="approve", id="cf-approve")
        yield Button("Deny", classes="deny", id="cf-deny")
        yield Button("Trust this session", id="cf-trust")
        yield Button("Permanently deny", id="cf-never")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        choice = {
            "cf-approve": "approve",
            "cf-deny": "deny",
            "cf-trust": "trust",
            "cf-never": "never",
        }.get(event.button.id)
        if choice:
            self._on_select(choice)

    def on_mount(self) -> None:
        self.query_one("#cf-approve", Button).focus()

    def on_key(self, event) -> None:
        """Explicit left/right navigation between choices and Enter to activate,
        so arrow keys work regardless of Textual's default focus migration."""
        buttons = [self.query_one("#cf-approve"), self.query_one("#cf-deny"),
                   self.query_one("#cf-trust"), self.query_one("#cf-never")]
        idx = next((i for i, b in enumerate(buttons) if b.has_focus), 0)
        if event.key == "left":
            buttons[(idx - 1) % len(buttons)].focus()
            event.stop()
        elif event.key == "right":
            buttons[(idx + 1) % len(buttons)].focus()
            event.stop()


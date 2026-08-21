# SPDX-License-Identifier: MIT
"""Custom Textual widgets for TUI interface."""

from __future__ import annotations

from typing import Callable

from rich.cells import cell_len
from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, Input, Static


class CommandSuggestionPopup(Static):
    """Floating popup listing matching slash commands. Not focusable: the
    Input keeps focus while ChatInput routes up/down/enter/escape to it.

    Long descriptions are truncated to a column budget (Rich cell_len counts
    CJK as two columns), because Textual's `text-wrap: nowrap` is a no-op here:
    the only real guarantee that each suggestion renders as exactly one row —
    keeping the row↔selection mapping intact — is that the line be no wider
    than the content area.
    """

    MAX_VISIBLE = 8
    CONTENT_WIDTH = 76  # popup width 80 minus border (2) and padding (2)

    DEFAULT_CSS = """
    CommandSuggestionPopup {
        dock: bottom;
        offset: 0 -4;
        width: 80;
        height: auto;
        max-height: 12;
        background: $surface;
        border: tall $primary;
        padding: 1;
    }
    """

    def __init__(self, suggestions: list[tuple[str, str]] | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.suggestions: list[tuple[str, str]] = suggestions or []
        self.selected = 0
        self._offset = 0
        self._paint()

    def set_suggestions(self, suggestions: list[tuple[str, str]]) -> None:
        """Replace the candidate list and reset the highlight to the first item."""
        self.suggestions = suggestions
        self.selected = 0
        self._offset = 0
        self._paint()

    def selected_command(self) -> str | None:
        """The command on the highlighted row, or None when empty."""
        if 0 <= self.selected < len(self.suggestions):
            return self.suggestions[self.selected][0]
        return None

    def move_cursor(self, delta: int) -> None:
        """Move the highlight by delta (wrapping), keeping it inside the viewport."""
        if not self.suggestions:
            return
        n = len(self.suggestions)
        self.selected = (self.selected + delta) % n
        self._offset = min(
            max(0, self.selected - self.MAX_VISIBLE + 1),
            max(0, n - self.MAX_VISIBLE),
        )
        self._paint()

    def _fit(self, cmd: str, desc: str) -> str:
        """Truncate desc in columns (not characters) so the whole row fits on
        one line within the content width."""
        budget = self.CONTENT_WIDTH - 3 - cell_len(cmd)  # marker (2) + gap (1)
        if cell_len(desc) <= budget:
            return desc
        out = ""
        for ch in desc:
            if cell_len(out) + cell_len(ch) + 1 > budget:
                break
            out += ch
        if out and not out.endswith("…"):
            out += "…"
        return out or "…"

    def _paint(self) -> None:
        visible = self.suggestions[self._offset : self._offset + self.MAX_VISIBLE]
        lines = []
        for row, (cmd, desc) in enumerate(visible):
            idx = self._offset + row
            shown = self._fit(cmd, desc)
            if idx == self.selected:
                lines.append(f"[bold reverse]▸ {cmd}[/] [dim reverse]{shown}[/]")
            else:
                lines.append(f"[bold cyan]  {cmd}[/] [dim]{shown}[/]")
        self.update("\n".join(lines))


class ChatInput(Input):
    """Input that drives the command-suggestion popup. While the popup is
    visible, up/down move the highlight, Enter runs the selected command, and
    Escape closes the popup. Keys fall through to Input normally otherwise."""

    _popup: CommandSuggestionPopup | None = None
    _on_pick: Callable[[str], None] | None = None
    _on_dismiss: Callable[[], None] | None = None

    def on_key(self, event: events.Key) -> None:
        popup = self._popup
        if popup is not None and popup.display and popup.suggestions:
            if event.key == "up":
                popup.move_cursor(-1)
                event.stop()
                return
            if event.key == "down":
                popup.move_cursor(1)
                event.stop()
                return
            if event.key == "enter":
                command = popup.selected_command()
                if command and self._on_pick is not None:
                    self._on_pick(command)
                event.stop()
                return
            if event.key == "escape":
                if self._on_dismiss is not None:
                    self._on_dismiss()
                event.stop()
                return


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


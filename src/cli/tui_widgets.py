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


# One (label, choice, css-class) per button. The choice is what the caller's
# on_select receives; the class only drives colour.
RISK_CONFIRM_OPTIONS = [
    ("Approve", "approve", "approve"),
    ("Deny", "deny", "deny"),
    ("Trust this session", "trust", ""),
    ("Permanently deny", "never", ""),
]

SANDBOX_ESCAPE_OPTIONS = [
    ("Allow once", "allow_once", "approve"),
    ("Deny", "deny", "deny"),
    ("Allow for this session", "allow_session", ""),
    ("Always allow this path", "allow_always", ""),
]


class ConfirmBar(Horizontal):
    """Bottom-docked approval bar that covers the input while a decision is
    pending. Choices are Buttons: arrow keys move the focus left/right,
    Enter/Space activates the focused button, mouse clicks select directly. The
    bar takes focus, so the Input underneath is not typable while a decision is
    outstanding — this blocks the turn until the user decides."""

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
                 on_select: Callable[[str], None],
                 options: list[tuple[str, str, str]] | None = None,
                 label: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._tool = tool
        self._args = args
        self._risk = risk
        self._on_select = on_select
        self._options = options or RISK_CONFIRM_OPTIONS
        self._label = label

    def compose(self) -> ComposeResult:
        label = self._label or (
            f"Requesting approval: [bold]{self._tool}[/] (risk={self._risk})\n"
            f"[dim]{self._args}[/]"
        )
        yield Static(label)
        for text, choice, css in self._options:
            yield Button(text, classes=css, id=f"cf-{choice}")

    def _buttons(self) -> list[Button]:
        return [self.query_one(f"#cf-{choice}", Button) for _, choice, _ in self._options]

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id.startswith("cf-"):
            self._on_select(button_id[len("cf-"):])

    def on_mount(self) -> None:
        self._buttons()[0].focus()

    def on_key(self, event) -> None:
        """Explicit left/right navigation between choices and Enter to activate,
        so arrow keys work regardless of Textual's default focus migration."""
        buttons = self._buttons()
        idx = next((i for i, b in enumerate(buttons) if b.has_focus), 0)
        if event.key == "left":
            buttons[(idx - 1) % len(buttons)].focus()
            event.stop()
        elif event.key == "right":
            buttons[(idx + 1) % len(buttons)].focus()
            event.stop()


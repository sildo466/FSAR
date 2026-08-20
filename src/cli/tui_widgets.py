# SPDX-License-Identifier: MIT
"""Custom Textual widgets for TUI interface."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static


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
    CommandSuggestionPopup > VerticalScroll {
        height: auto;
    }
    .suggestion-item {
        padding: 0 1;
        color: $text;
    }
    .suggestion-cmd {
        color: $accent;
        text-style: bold;
    }
    .suggestion-desc {
        color: $text-muted;
    }
    """

    def __init__(self, suggestions: list[tuple[str, str]] | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.suggestions = suggestions or []

    def compose(self) -> ComposeResult:
        with VerticalScroll():
            for cmd, desc in self.suggestions:
                line = f"[cyan bold]{cmd}[/] [dim]{desc}[/]"
                yield Static(line, classes="suggestion-item")

    def set_suggestions(self, suggestions: list[tuple[str, str]]) -> None:
        """Replace rendered suggestions (no re-mount)."""
        self.suggestions = suggestions
        lines = [
            f"[cyan bold]{cmd}[/] [dim]{desc}[/]" for cmd, desc in suggestions
        ]
        self.update("\n".join(lines))

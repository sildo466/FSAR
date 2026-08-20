# SPDX-License-Identifier: MIT
"""Custom Textual widgets for TUI interface."""

from __future__ import annotations

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

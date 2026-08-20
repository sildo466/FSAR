# SPDX-License-Identifier: MIT
"""Command prediction and suggestion system for TUI slash commands."""

from __future__ import annotations

COMMANDS = {
    "/help": "Show available commands",
    "/exit": "Exit the application",
    "/quit": "Exit the application",
    "/model": "Select LLM model",
    "/character": "Select character card",
    "/user": "Select user card",
    "/tier": "Set agent tier (low|medium|high|xhigh|max)",
    "/effort": "Set reasoning effort (low|medium|high|xhigh|max)",
    "/compact": "Compact conversation history",
    "/reset": "Clear conversation history",
    "/resume": "Resume historical conversation",
    "/permissions": "Configure sandbox permissions",
}


class CommandPredictor:
    """Predict and suggest slash commands based on partial input."""

    def predict(self, text: str) -> list[tuple[str, str]]:
        """Return [(command, description), ...] matching the input prefix."""
        if not text.startswith("/"):
            return []

        prefix = text.lower()
        matches = [
            (cmd, desc)
            for cmd, desc in COMMANDS.items()
            if cmd.startswith(prefix)
        ]

        return matches[:5]

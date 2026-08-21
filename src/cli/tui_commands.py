# SPDX-License-Identifier: MIT
"""Command prediction and suggestion system for TUI slash commands."""

from __future__ import annotations

COMMANDS = {
    # UI-level commands (dispatched by ChatApp).
    "/help": "Show available commands",
    "/exit": "Exit the application",
    "/quit": "Exit the application",
    "/model": "Select LLM model",
    "/character": "Select character card",
    "/user": "Select user card",
    "/tier": "Set agent tier (low|medium|high|xhigh|max|ultra)",
    "/effort": "Set reasoning effort (low|medium|high|xhigh|max)",
    "/compact": "Compact conversation history",
    "/new": "Start a new conversation",
    "/resume": "Resume historical conversation",
    "/permissions": "Configure sandbox permissions",
    # Engine-level commands (dispatched by server/handlers/commands.py);
    # typed in chat they route through the engine, so they work here too.
    "/memory": "Inspect/manage the memory database",
    "/history": "Recent messages in current session",
    "/search": "Search long-term memory",
    "/clear": "Clear current conversation context",
    "/config": "Show active LLM provider config",
    "/tools": "List available tools",
    "/mcp": "MCP server status / reload",
    "/perm": "Permissions: trust / deny / grant / reset",
    "/audit": "Recent audit log",
    "/rate": "Rate the most recent reply (1-5)",
    "/profile": "View / set user profile",
    "/prefs": "View / set preferences",
    "/feedback": "Rating statistics",
    "/reflect": "Force immediate reflection",
    "/stats": "Tool decision-log aggregates",
    "/exp": "Experiences CRUD (view / del / archive)",
    "/use": "Load a learned skill/experience into context",
    "/learn": "Persist an experience",
    "/import": "Import an external skill",
    "/remember": "Persist a cross-session fact",
    "/facts": "List / search saved facts",
    "/skills": "External skills status / activity",
}


class CommandPredictor:
    """Predict and suggest slash commands based on partial input."""

    def predict(self, text: str) -> list[tuple[str, str]]:
        """Return [(command, description), ...] matching the input prefix."""
        if not text.startswith("/"):
            return []

        prefix = text.lower()
        return [
            (cmd, desc)
            for cmd, desc in COMMANDS.items()
            if cmd.startswith(prefix)
        ]

# SPDX-License-Identifier: MIT
"""Command prediction and suggestion system for TUI slash commands.

Three sources feed the palette:
- UI-level commands (dispatched by ChatApp itself) — a fixed TUI constant.
- Engine-level commands — derived live from the server command registry so the
  list can never drift from what the engine actually handles.
- Installed skills/experiences — queried from the experience store, surfaced as
  ``/use <name>`` entries, so installed skills appear without touching code.
"""

from __future__ import annotations

import time

UI_COMMANDS = {
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
}

_ENGINE_CODE = None
_ENGINE_CACHE: dict[str, str] | None = None
_SKILL_CACHE: dict[str, str] | None = None
_SKILL_CACHE_AT = 0.0
_SKILL_TTL = 5.0


def engine_commands() -> dict[str, str]:
    """Every command the engine can execute, keyed by command string. Derived
    from the handler registry so new engine commands show up automatically."""
    global _ENGINE_CODE, _ENGINE_CACHE
    if _ENGINE_CACHE is not None:
        return _ENGINE_CACHE
    try:
        if _ENGINE_CODE is None:
            from src.server.handlers.commands import (  # noqa: PLC0415
                COMMAND_DESCRIPTIONS,
                _HANDLERS,
            )

            _ENGINE_CODE = (_HANDLERS, COMMAND_DESCRIPTIONS)
        handlers, descriptions = _ENGINE_CODE
        _ENGINE_CACHE = {
            cmd: descriptions.get(cmd, "") for cmd in handlers
        }
    except Exception:  # server package unavailable — prediction keeps working
        _ENGINE_CACHE = {}
    return _ENGINE_CACHE


def skill_commands() -> dict[str, str]:
    """Installed skills as ``/use <name>`` palette entries, cached briefly so
    keystrokes do not re-query SQLite per character."""
    global _SKILL_CACHE, _SKILL_CACHE_AT
    now = time.monotonic()
    if _SKILL_CACHE is not None and now - _SKILL_CACHE_AT < _SKILL_TTL:
        return _SKILL_CACHE
    try:
        from src.memory import ExperienceStore  # noqa: PLC0415

        entries: dict[str, str] = {}
        for exp in ExperienceStore().list_for_index(
            categories=["external-skill"],
            include_states=["active", "stale"],
        ):
            name = (getattr(exp, "name", "") or "").strip()
            if name:
                desc = (getattr(exp, "description", "") or "").strip()
                if len(desc) > 48:
                    desc = f"{desc[:48].rstrip()}…"
                entries[f"/use {name}"] = desc or "Learned skill/experience"
        _SKILL_CACHE = entries
    except Exception:  # store unreachable — fall back to no dynamic skills
        _SKILL_CACHE = {}
    _SKILL_CACHE_AT = now
    return _SKILL_CACHE


class CommandPredictor:
    """Predict and suggest slash commands based on partial input."""

    def all_commands(self) -> dict[str, str]:
        """Merged palette: UI commands win name conflicts, skills last."""
        return {**UI_COMMANDS, **engine_commands(), **skill_commands()}

    def predict(self, text: str) -> list[tuple[str, str]]:
        """Return [(command, description), ...] matching the input prefix."""
        if not text.startswith("/"):
            return []

        prefix = text.lower()
        return [
            (cmd, desc)
            for cmd, desc in self.all_commands().items()
            if cmd.startswith(prefix)
        ]
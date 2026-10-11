# SPDX-License-Identifier: MIT
"""A room turn decides from risk level; the owner's own turn keeps per-tool trust."""

from __future__ import annotations

from types import SimpleNamespace

from src.security.permissions import load_permissions
from src.security.risk import RiskEngine


def _state(tmp_path):
    """DEFAULT_PERMISSIONS, whatever this machine's permissions.yaml says.

    Pointing at a path that does not exist is the public way to get the
    defaults back; reading the ambient file would make these tests depend on
    the developer's own settings.
    """
    return load_permissions(tmp_path / "permissions.yaml")


def _tool(name: str, risk: str):
    return SimpleNamespace(name=name, risk_level=risk, server_name=None)


def test_room_turn_asks_for_medium_even_when_the_tool_is_trusted(tmp_path):
    """file_ops.read is `trust` in the default table; a room turn must not
    inherit that, or the box's ordinary file reads would never be reviewed."""
    state = _state(tmp_path)
    assert state.mode == "normal"
    assert state.tool_mode("file_ops", "read") == "trust"

    engine = RiskEngine(state)
    args = {"operation": "read", "path": "notes.txt"}

    own = engine.evaluate(_tool("file_ops", "MEDIUM"), dict(args))
    assert own.action == "proceed", "the owner's own turn keeps the trust shortcut"

    room = engine.evaluate(_tool("file_ops", "MEDIUM"), dict(args), room_turn=True)
    assert room.action == "confirm"
    assert room.needs_confirm()


def test_room_turn_lets_the_owner_opt_out_with_trust_mode(tmp_path):
    state = _state(tmp_path)
    state.mode = "trust"
    engine = RiskEngine(state)

    verdict = engine.evaluate(
        _tool("file_ops", "MEDIUM"), {"operation": "read"}, room_turn=True,
    )
    assert verdict.action == "proceed", "an explicit trust mode is the owner's call"


def test_room_turn_lets_safe_tools_through(tmp_path):
    engine = RiskEngine(_state(tmp_path))
    verdict = engine.evaluate(_tool("web_search", "SAFE"), {}, room_turn=True)
    assert verdict.action == "proceed"


def test_room_turn_still_honours_deny_and_blocked_patterns(tmp_path):
    """The room branch must not sit in front of the hard stops."""
    engine = RiskEngine(_state(tmp_path))
    verdict = engine.evaluate(
        _tool("run_command", "HIGH"), {"command": "rm -rf /"}, room_turn=True,
    )
    assert verdict.action == "deny"
    assert verdict.rule_matched == "blocked_pattern"

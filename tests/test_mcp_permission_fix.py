"""Tests for the MCP-permission fix (P6+).

Covers:
  1. PermissionState.tool_mode returns None for unknown tools (so RiskEngine
     falls through to threshold check instead of unconditionally confirming).
  2. server_trust is honored by tool_mode and cleared by clear_session.
  3. RiskEngine proceeds for unknown LOW MCP tools (the original complaint) and
     still confirms for unknown HIGH MCP tools.
  4. RiskEngine honors server_trust (per-server trust bypasses per-tool lookup).
  5. confirmation.ask_user exposes [server] only when server_name is provided
     and emits ConfirmResponse.SERVER_TRUST.
"""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.security.confirmation import ConfirmResponse, ask_user
from src.security.permissions import PermissionState
from src.security.risk import LOW, HIGH, MEDIUM, RiskEngine
from src.tools.registry import Tool


class _StubTool(Tool):
    """Minimal Tool stub. Optionally carries a server_name for MCPTool-like tests."""

    def __init__(self, name: str, risk: str = MEDIUM, server_name: str | None = None):
        self._name = name
        self._risk = risk
        self._server_name = server_name

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "stub"

    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {}}

    @property
    def risk_level(self) -> str:
        return self._risk

    @property
    def server_name(self) -> str | None:
        return self._server_name

    async def execute(self, **kwargs) -> str:
        return "ok"


def _input_async(value: str):
    """Build a coroutine that returns `value` (simulates user typing)."""

    async def _coro():
        return value

    return _coro()


# ---------- PermissionState ----------


def test_tool_mode_unknown_returns_none():
    """Unknown tool → None (NOT "ask"), so RiskEngine can do threshold check."""
    state = PermissionState()
    assert state.tool_mode("mcp__srv__never_seen") is None


def test_tool_mode_known_returns_yaml_mode():
    state = PermissionState(tools={"edit": {"mode": "ask"}})
    assert state.tool_mode("edit") == "ask"


def test_tool_mode_session_deny_wins():
    state = PermissionState(
        tools={"x": {"mode": "trust"}},
        session_deny={"x"},
    )
    assert state.tool_mode("x") == "deny"


def test_tool_mode_session_trust_overrides_yaml():
    state = PermissionState(tools={"x": {"mode": "ask"}})
    state.set_session_trust("x")
    assert state.tool_mode("x") == "trust"


def test_server_trust_overrides_yaml_for_unlisted_tool():
    """Unknown MCP tool becomes trust when its server is in server_trust."""
    state = PermissionState()
    state.set_server_trust("everything")
    assert state.tool_mode("mcp__everything__echo", server_name="everything") == "trust"


def test_server_trust_cleared_by_clear_session():
    state = PermissionState()
    state.set_server_trust("everything")
    state.clear_session()
    assert "everything" not in state.server_trust
    assert state.tool_mode("mcp__everything__echo", server_name="everything") is None


# ---------- RiskEngine ----------


def test_riskengine_unknown_low_mcp_proceeds():
    """The original bug: an unknown MCP tool with risk=LOW should NOT prompt in normal mode."""
    state = PermissionState(mode="normal")
    engine = RiskEngine(state)
    tool = _StubTool("mcp__everything__echo", risk=LOW, server_name="everything")
    verdict = engine.evaluate(tool, {})
    assert verdict.action == "proceed", (
        f"LOW-risk unknown MCP tool should proceed, got {verdict.action} ({verdict.reason})"
    )


def test_riskengine_unknown_high_mcp_confirms():
    """Unknown MCP tool with risk=HIGH still confirms in normal mode."""
    state = PermissionState(mode="normal")
    engine = RiskEngine(state)
    tool = _StubTool("mcp__github__create_issue", risk=HIGH, server_name="github")
    verdict = engine.evaluate(tool, {})
    assert verdict.action == "confirm"


def test_riskengine_known_ask_mode_still_confirms():
    """Explicit yaml mode='ask' must still confirm (don't weaken existing semantics)."""
    state = PermissionState(tools={"run_command": {"mode": "ask", "risk": "HIGH"}})
    engine = RiskEngine(state)
    tool = _StubTool("run_command", risk=HIGH)
    verdict = engine.evaluate(tool, {})
    assert verdict.action == "confirm"


def test_riskengine_server_trust_lets_unlisted_tool_proceed():
    """Trusting a server makes every tool from that server proceed, even without per-tool trust."""
    state = PermissionState(mode="normal")
    state.set_server_trust("everything")
    engine = RiskEngine(state)
    tool = _StubTool("mcp__everything__sum", risk=LOW, server_name="everything")
    verdict = engine.evaluate(tool, {})
    assert verdict.action == "proceed"


def test_riskengine_strict_mode_still_asks_low():
    """session.mode=strict still asks for LOW unknown tools (conservative)."""
    state = PermissionState(mode="strict")
    engine = RiskEngine(state)
    tool = _StubTool("mcp__everything__echo", risk=LOW, server_name="everything")
    verdict = engine.evaluate(tool, {})
    assert verdict.action == "confirm"


# ---------- ask_user ----------


def test_ask_user_server_option_only_when_server_name_set():
    """[server] is hidden when server_name is None."""
    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with patch("asyncio.get_event_loop") as loop:
        loop.return_value.run_in_executor.return_value = _input_async("y")
        with redirect_stdout(buf):
            asyncio.run(ask_user("mcp__x__echo", {}, "reason"))

    out = buf.getvalue()
    assert "[server]" not in out
    assert "[all]" in out


def test_ask_user_server_option_visible_when_server_name_set():
    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with patch("asyncio.get_event_loop") as loop:
        loop.return_value.run_in_executor.return_value = _input_async("y")
        with redirect_stdout(buf):
            asyncio.run(
                ask_user("mcp__x__echo", {}, "reason", server_name="x")
            )

    out = buf.getvalue()
    assert "[server]" in out
    assert "'x'" in out


def test_ask_user_server_input_triggers_callback():
    state = PermissionState()
    called: list[str] = []

    def _on_server_trust(name: str) -> None:
        called.append(name)
        state.set_server_trust(name)

    with patch("asyncio.get_event_loop") as loop:
        loop.return_value.run_in_executor.return_value = _input_async("server")
        result = asyncio.run(
            ask_user(
                "mcp__everything__echo",
                {},
                "reason",
                on_server_trust=_on_server_trust,
                server_name="everything",
            )
        )

    assert result.response == ConfirmResponse.SERVER_TRUST
    assert called == ["everything"]
    assert "everything" in state.server_trust


def test_ask_user_server_input_ignored_when_no_server_name():
    """Typing 'server' without a server_name falls through to default deny."""
    with patch("asyncio.get_event_loop") as loop:
        loop.return_value.run_in_executor.return_value = _input_async("server")
        result = asyncio.run(ask_user("tool", {}, "reason"))

    assert result.response == ConfirmResponse.NO


if __name__ == "__main__":
    # Function-style tests — call each one and report failures explicitly.
    import inspect

    funcs = [
        (n, o)
        for n, o in globals().items()
        if inspect.isfunction(o) and n.startswith("test_")
    ]
    failures = []
    for name, fn in funcs:
        try:
            fn()
        except Exception as e:
            failures.append((name, e))
            print(f"FAIL  {name}: {e}")
        else:
            print(f"PASS  {name}")
    if failures:
        print(f"\n{len(failures)}/{len(funcs)} tests failed")
        sys.exit(1)
    print(f"\nAll {len(funcs)} tests passed")
    sys.exit(0)
"""Cross-platform tests for the run_command tool."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_default_shell_posix_is_bash(monkeypatch):
    import src.tools.builtin.run_command as rc

    monkeypatch.setattr(rc.sys, "platform", "linux")
    assert rc._default_shell() == "bash"


def test_default_shell_windows_is_powershell(monkeypatch):
    import src.tools.builtin.run_command as rc

    monkeypatch.setattr(rc.sys, "platform", "win32")
    assert rc._default_shell() == "powershell"


def test_valid_shells_are_platform_specific(monkeypatch):
    import src.tools.builtin.run_command as rc

    monkeypatch.setattr(rc.sys, "platform", "linux")
    assert rc._valid_shells() == {"bash"}

    monkeypatch.setattr(rc.sys, "platform", "win32")
    assert rc._valid_shells() == {"powershell", "cmd", "bash"}


def test_parameters_advertise_current_platform_shells(monkeypatch):
    import src.tools.builtin.run_command as rc

    tool = rc.RunCommandTool()
    monkeypatch.setattr(rc.sys, "platform", "linux")
    assert tool.parameters["properties"]["shell"] == {
        "type": "string",
        "enum": ["bash"],
        "default": "bash",
        "description": "Shell to use for execution",
    }

    monkeypatch.setattr(rc.sys, "platform", "win32")
    assert tool.parameters["properties"]["shell"]["enum"] == [
        "bash",
        "cmd",
        "powershell",
    ]
    assert tool.parameters["properties"]["shell"]["default"] == "powershell"


def test_execute_rejects_invalid_shell_before_guard(monkeypatch):
    import src.tools.builtin.run_command as rc

    async def unexpected_guard(*args, **kwargs):
        raise AssertionError("guard_command must not run for an invalid shell")

    monkeypatch.setattr(rc.sys, "platform", "linux")
    monkeypatch.setattr(rc, "guard_command", unexpected_guard)

    result = asyncio.run(
        rc.RunCommandTool().execute("echo hello", shell="powershell")
    )

    assert result == "Error: shell 'powershell' not supported on this platform"


def test_decode_output_uses_platform_scoped_fallbacks(monkeypatch):
    import src.tools.builtin.run_command as rc

    gbk_data = "中文".encode("gbk")
    monkeypatch.setattr(rc.sys, "platform", "linux")
    assert rc._decode_output(gbk_data) == gbk_data.decode("utf-8", errors="replace")

    monkeypatch.setattr(rc.sys, "platform", "win32")
    assert rc._decode_output(gbk_data) == "中文"

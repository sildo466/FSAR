"""Cross-platform tests for process tool shell selection."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class _EmptyStdout:
    async def readline(self) -> bytes:
        return b""


class _CompletedProcess:
    stdout = _EmptyStdout()
    returncode = 0


def test_shell_helpers_and_schema_follow_current_platform(monkeypatch):
    import src.tools.builtin.process as process

    monkeypatch.setattr(process.sys, "platform", "linux")

    assert process._default_shell() == "bash"
    assert process._valid_shells() == {"bash"}
    assert process.ProcessTool().parameters["properties"]["shell"] == {
        "type": "string",
        "enum": ["bash"],
        "default": "bash",
        "description": "Shell to use",
    }

    monkeypatch.setattr(process.sys, "platform", "win32")

    assert process._default_shell() == "powershell"
    assert process._valid_shells() == {"powershell", "cmd", "bash"}
    assert process.ProcessTool().parameters["properties"]["shell"]["enum"] == [
        "bash",
        "cmd",
        "powershell",
    ]
    assert process.ProcessTool().parameters["properties"]["shell"]["default"] == "powershell"


def test_process_tool_rejects_invalid_shell_without_creating_subprocess(monkeypatch):
    import src.tools.builtin.process as process

    called = False

    async def fake_create_subprocess_exec(*args, **kwargs):
        nonlocal called
        called = True
        return _CompletedProcess()

    monkeypatch.setattr(process.sys, "platform", "linux")
    monkeypatch.setattr(process.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(process, "process_manager", process.ProcessManager())

    result = asyncio.run(process.ProcessTool().execute("start", "echo hello", shell="cmd"))

    assert result == "Error: shell 'cmd' not supported on this platform"
    assert called is False


def test_process_manager_uses_platform_default_shell_at_subprocess_boundary(monkeypatch):
    import src.tools.builtin.process as process

    captured = []

    async def fake_create_subprocess_exec(*args, **kwargs):
        captured.append((args, kwargs))
        return _CompletedProcess()

    async def start_and_drain() -> str:
        result = await process.ProcessManager().start("echo hello")
        await asyncio.sleep(0)
        return result

    monkeypatch.setattr(process.sys, "platform", "linux")
    monkeypatch.setattr(process.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    assert asyncio.run(start_and_drain()) == "Started process 1: echo hello"
    assert captured == [
        (("bash", "-c", "echo hello"), {"stdout": process.subprocess.PIPE, "stderr": process.subprocess.STDOUT})
    ]

"""FSAR run_command tool — execute shell/powershell commands with timeout."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import tempfile
from typing import Optional

from src.tools.registry import Tool
from src.sandbox.tool_guard import guard_command
from src.utils.logger import logger
from src.utils.process_kill import kill_process_tree


def _default_shell() -> str:
    if sys.platform == "win32":
        return "powershell"
    return "bash"


def _valid_shells() -> set[str]:
    if sys.platform == "win32":
        return {"powershell", "cmd", "bash"}
    return {"bash"}


def _decode_output(data: bytes) -> str:
    """Decode subprocess output with Windows codepage fallbacks when needed."""
    encodings = (
        ("utf-8", "gbk", "cp936", "latin-1")
        if sys.platform == "win32"
        else ("utf-8",)
    )
    for enc in encodings:
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


class RunCommandTool(Tool):
    """Execute shell or powershell commands."""

    @property
    def name(self) -> str:
        return "run_command"

    @property
    def description(self) -> str:
        return "Execute a shell or powershell command. Use for system commands, file operations, URL schemes, etc."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The command to execute",
                },
                "shell": {
                    "type": "string",
                    "enum": sorted(_valid_shells()),
                    "default": _default_shell(),
                    "description": "Shell to use for execution",
                },
                "timeout": {
                    "type": "integer",
                    "default": 30,
                    "description": "Timeout in seconds",
                },
            },
            "required": ["command"],
        }

    @property
    def risk_level(self) -> str:
        return "HIGH"

    async def execute(self, command: str = "", shell: str | None = None, timeout: int = 30, **kwargs) -> str:
        """Execute a shell command and return the output."""
        if not command or not command.strip():
            return "Error: command is required"
        if shell is None:
            shell = _default_shell()
        if shell not in _valid_shells():
            return f"Error: shell {shell!r} not supported on this platform"
        blocked = await guard_command(command, shell, kwargs)
        if blocked:
            return blocked
        sandbox_cwd = kwargs.get("_sandbox_cwd")
        context = kwargs.get("session_ctx")
        if not sandbox_cwd and context is not None:
            workspace = context.workspace_gate.workspace_repo.get(context.active_workspace_id)
            sandbox_cwd = workspace.root_path if workspace else None
        bat_path: Optional[str] = None
        try:
            if shell == "powershell":
                # Windows PowerShell 5.x defaults its console output encoding to
                # the system codepage (e.g. GBK). Force UTF-8 so non-ASCII output
                # round-trips correctly.
                ps_command = (
                    "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
                    "$OutputEncoding = [System.Text.Encoding]::UTF8; "
                    + command
                )
                cmd_list = ["powershell", "-NoProfile", "-Command", ps_command]
            elif shell == "cmd":
                # Windows cmd cannot pass non-ASCII args reliably through its
                # argv (CreateProcess ANSI path) — Chinese path components get
                # mangled before cmd ever sees them. Workaround: write the
                # command to a UTF-8 .bat file with `chcp 65001`, then exec
                # the file path (which is ASCII-only on argv).
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".bat", delete=False, encoding="utf-8"
                ) as f:
                    f.write("@echo off\r\nchcp 65001 >nul\r\n")
                    f.write(command)
                    if not command.endswith("\r\n"):
                        f.write("\r\n")
                    bat_path = f.name
                cmd_list = ["cmd", "/c", bat_path]
            elif shell == "bash":
                cmd_list = ["bash", "-c", command]
            else:
                return f"Error: Unknown shell '{shell}'"

            logger.info(f"Executing: {command} (shell={shell}, timeout={timeout})")

            proc = await asyncio.create_subprocess_exec(
                *cmd_list,
                cwd=sandbox_cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )

            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                kill_process_tree(proc.pid)
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    pass
                return f"Error: Command timed out after {timeout}s"

            stdout_str = _decode_output(stdout).strip()
            stderr_str = _decode_output(stderr).strip()

            if proc.returncode != 0:
                output = f"Exit code: {proc.returncode}\n"
                if stdout_str:
                    output += f"stdout:\n{stdout_str}\n"
                if stderr_str:
                    output += f"stderr:\n{stderr_str}"
                return output.strip()

            if stdout_str and stderr_str:
                return f"{stdout_str}\n\nstderr:\n{stderr_str}"
            elif stdout_str:
                return stdout_str
            elif stderr_str:
                return f"stderr:\n{stderr_str}"
            else:
                return "Command executed successfully (no output)"

        except Exception as e:
            logger.error(f"Command execution failed: {e}")
            return f"Error: {e}"
        finally:
            if bat_path:
                try:
                    os.remove(bat_path)
                except OSError:
                    pass

"""FSAR run_command tool — execute shell/powershell commands with timeout."""

from __future__ import annotations

import asyncio
import base64
import os
import re
import shutil
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


def _unwrap_shell_wrapper(command: str, shell: str) -> str:
    """Strip a redundant self-wrapper like `powershell -Command "..."`.

    Commands occasionally arrive already wrapped (e.g. `powershell -Command
    "$p = ..."`). Executing that string through another `powershell -Command`
    layer makes the outer shell interpolate every `$var` (to empty) and eat
    `$_` before the inner command ever runs. When the whole command is a
    single-argument wrapper, unwrap it so the inner script executes directly.
    """
    if shell == "powershell":
        prefix = re.compile(
            r"^\s*(?:powershell|pwsh)(?:\.exe)?\s+"
            r"(?:-(?:NoProfile|NonInteractive|ExecutionPolicy\s+\S+)\s+)*"
            r"-(?:Command|c)\s+",
            re.IGNORECASE,
        )
    elif shell == "bash":
        prefix = re.compile(
            r"^\s*(?:bash|sh|/bin/(?:ba)?sh)\s+-c\s+", re.IGNORECASE,
        )
    elif shell == "cmd":
        prefix = re.compile(r"^\s*cmd(?:\.exe)?\s+/c\s+", re.IGNORECASE)
    else:
        return command

    match = prefix.match(command)
    if not match:
        return command
    rest = command[match.end():]
    if not rest or rest[0] not in "\"'":
        return command
    quote = rest[0]
    inner: list[str] = []
    i = 1
    closed = False
    while i < len(rest):
        ch = rest[i]
        if quote == '"' and ch == "\\" and i + 1 < len(rest) and rest[i + 1] in {'"', "\\"}:
            inner.append(rest[i + 1])
            i += 2
            continue
        if quote == "'" and ch == "'" and i + 1 < len(rest) and rest[i + 1] == "'":
            inner.append("'")
            i += 2
            continue
        if ch == quote:
            closed = True
            i += 1
            break
        inner.append(ch)
        i += 1
    if not closed:
        return command
    if rest[i:].strip():
        return command
    return "".join(inner)


def _decode_output(data: bytes) -> str:
    """Decode subprocess output with BOM sniffing and codepage fallbacks."""
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig")
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        return data.decode("utf-16")
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


_POWER_SHELL_SHIMS = (
    "$ProgressPreference = 'SilentlyContinue'; "
    "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
    "$OutputEncoding = [System.Text.Encoding]::UTF8; "
    "$PSDefaultParameterValues['*:Encoding'] = 'utf8'; "
)


def _powershell_argv(command: str, *, exe: str | None = None) -> list[str]:
    """Build an argv that runs `command` without codepage/quoting loss.

    The command travels as -EncodedCommand (base64 UTF-16LE), so non-ASCII
    characters and $variables survive untouched even on Windows PowerShell
    5.1, whose -Command argv path re-encodes through the ANSI codepage.
    pwsh (PowerShell 7+) is used when present; 5.1 gets UTF-8 shims so stdout
    and file-writing cmdlets (Out-File/Set-Content/Export-Csv, which default
    to UTF-16 on 5.1) produce UTF-8 instead of NUL-laden text.
    """
    if exe is None:
        exe = shutil.which("pwsh") or "powershell"
    inner = _POWER_SHELL_SHIMS + command
    encoded = base64.b64encode(inner.encode("utf-16-le")).decode("ascii")
    return [exe, "-NoProfile", "-EncodedCommand", encoded]


class RunCommandTool(Tool):
    """Execute shell or powershell commands."""

    @property
    def name(self) -> str:
        return "run_command"

    @property
    def description(self) -> str:
        return ("Execute a shell or powershell command. Use for system commands, file operations, URL schemes, etc. "
                "Pass the raw script for the chosen shell: do NOT wrap the command in "
                "'powershell -Command \"...\"', 'bash -c \"...\"' or 'cmd /c \"...\"' — "
                "the command already runs directly in the shell; wrapping double-interpolates "
                "variables like $var and $_ and they become empty.")

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
        command = _unwrap_shell_wrapper(command, shell)
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
                cmd_list = _powershell_argv(command)
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

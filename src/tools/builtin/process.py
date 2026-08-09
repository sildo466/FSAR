"""FSAR process tool — background process management."""

from __future__ import annotations

import asyncio
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.sandbox.tool_guard import guard_command
from src.tools.registry import Tool
from src.utils.logger import logger


def _default_shell() -> str:
    if sys.platform == "win32":
        return "powershell"
    return "bash"


def _valid_shells() -> set[str]:
    if sys.platform == "win32":
        return {"powershell", "cmd", "bash"}
    return {"bash"}


@dataclass
class BackgroundProcess:
    """A tracked background process."""
    id: str
    command: str
    process: asyncio.subprocess.Process
    started_at: float = field(default_factory=time.time)
    output: List[str] = field(default_factory=list)
    done: bool = False
    return_code: Optional[int] = None


class ProcessManager:
    """Manage background processes."""

    def __init__(self):
        self._processes: Dict[str, BackgroundProcess] = {}

    def _next_id(self) -> str:
        """Generate next process ID."""
        existing = [int(k) for k in self._processes.keys() if k.isdigit()]
        return str(max(existing, default=0) + 1)

    async def start(self, command: str, shell: str | None = None) -> str:
        """Start a background process."""
        if shell is None:
            shell = _default_shell()
        if shell not in _valid_shells():
            return f"Error: shell {shell!r} not supported on this platform"

        proc_id = self._next_id()

        if shell == "powershell":
            cmd_list = ["powershell", "-NoProfile", "-Command", command]
        elif shell == "cmd":
            cmd_list = ["cmd", "/c", command]
        else:
            cmd_list = ["bash", "-c", command]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd_list,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )

            bg = BackgroundProcess(
                id=proc_id,
                command=command,
                process=process,
            )
            self._processes[proc_id] = bg

            # Start reader task
            asyncio.create_task(self._read_output(bg))

            logger.info(f"Started background process {proc_id}: {command}")
            return f"Started process {proc_id}: {command}"

        except Exception as e:
            logger.error(f"Failed to start process: {e}")
            return f"Error: {e}"

    async def _read_output(self, bg: BackgroundProcess):
        """Read process output continuously."""
        try:
            while True:
                line = await bg.process.stdout.readline()
                if not line:
                    break
                bg.output.append(line.decode("utf-8", errors="replace").rstrip())
        except Exception:
            pass
        finally:
            bg.done = True
            bg.return_code = bg.process.returncode

    def list_processes(self) -> str:
        """List all tracked processes."""
        if not self._processes:
            return "No running processes"

        lines = []
        for pid, bg in self._processes.items():
            status = "running" if not bg.done else f"done (exit {bg.return_code})"
            elapsed = time.time() - bg.started_at
            lines.append(f"[{pid}] {status} ({elapsed:.1f}s) - {bg.command[:60]}")

        return "\n".join(lines)

    def get_log(self, proc_id: str, tail: int = 20) -> str:
        """Get process output log."""
        bg = self._processes.get(proc_id)
        if not bg:
            return f"Error: Process {proc_id} not found"

        if not bg.output:
            return f"Process {proc_id}: (no output yet)"

        lines = bg.output[-tail:]
        return f"Process {proc_id} output (last {tail}):\n" + "\n".join(lines)

    def poll(self, proc_id: str) -> str:
        """Poll process status."""
        bg = self._processes.get(proc_id)
        if not bg:
            return f"Error: Process {proc_id} not found"

        if bg.done:
            return f"Process {proc_id} finished with exit code {bg.return_code}"

        # Check if still running
        if bg.process.returncode is not None:
            bg.done = True
            bg.return_code = bg.process.returncode
            return f"Process {proc_id} finished with exit code {bg.return_code}"

        elapsed = time.time() - bg.started_at
        return f"Process {proc_id} still running ({elapsed:.1f}s)"

    async def kill(self, proc_id: str) -> str:
        """Kill a process."""
        bg = self._processes.get(proc_id)
        if not bg:
            return f"Error: Process {proc_id} not found"

        if bg.done:
            return f"Process {proc_id} already finished"

        try:
            bg.process.terminate()
            try:
                await asyncio.wait_for(bg.process.wait(), timeout=3)
            except asyncio.TimeoutError:
                bg.process.kill()
                await bg.process.wait()

            bg.done = True
            bg.return_code = bg.process.returncode
            logger.info(f"Killed process {proc_id}")
            return f"Killed process {proc_id}"

        except Exception as e:
            return f"Error killing process: {e}"

    async def kill_all(self) -> str:
        """Kill all running processes."""
        killed = []
        for pid, bg in list(self._processes.items()):
            if not bg.done:
                await self.kill(pid)
                killed.append(pid)

        if killed:
            return f"Killed processes: {', '.join(killed)}"
        return "No running processes to kill"


# Global process manager
process_manager = ProcessManager()


class ProcessTool(Tool):
    """Manage background processes."""

    @property
    def name(self) -> str:
        return "process"

    @property
    def description(self) -> str:
        return ("Manage background processes. Actions: "
                "start (run command in background), "
                "list (show running processes), "
                "log (get process output), "
                "poll (check status), "
                "kill (terminate process).")

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["start", "list", "log", "poll", "kill", "kill_all"],
                    "description": "Action to perform",
                },
                "command": {
                    "type": "string",
                    "description": "Command to run (for start action)",
                },
                "process_id": {
                    "type": "string",
                    "description": "Process ID (for log/poll/kill actions)",
                },
                "tail": {
                    "type": "integer",
                    "default": 20,
                    "description": "Number of log lines to return",
                },
                "shell": {
                    "type": "string",
                    "enum": sorted(_valid_shells()),
                    "default": _default_shell(),
                    "description": "Shell to use",
                },
            },
            "required": ["action"],
        }

    @property
    def risk_level(self) -> str:
        return "MEDIUM"

    async def execute(self, action: str, command: str = "", process_id: str = "",
                      tail: int = 20, shell: str | None = None, **kwargs) -> str:
        """Execute process management action."""
        if shell is None:
            shell = _default_shell()

        if action == "start":
            if not command:
                return "Error: command is required for start action"
            blocked = await guard_command(command, shell, kwargs)
            if blocked:
                return blocked
            return await process_manager.start(command, shell)

        elif action == "list":
            return process_manager.list_processes()

        elif action == "log":
            if not process_id:
                return "Error: process_id is required for log action"
            return process_manager.get_log(process_id, tail)

        elif action == "poll":
            if not process_id:
                return "Error: process_id is required for poll action"
            return process_manager.poll(process_id)

        elif action == "kill":
            if not process_id:
                return "Error: process_id is required for kill action"
            return await process_manager.kill(process_id)

        elif action == "kill_all":
            return await process_manager.kill_all()

        else:
            return f"Error: Unknown action '{action}'"

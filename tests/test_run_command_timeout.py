"""Tests for run_command/process tree-kill on timeout.

Interactive commands (npx -> node, etc.) spawn grandchildren that inherit the
stdout/stderr pipe write end. Killing only the direct child leaves the
grandchild holding the pipe, so the reader never sees EOF and the coroutine
hangs past the timeout. These tests verify the tree-kill helper and that
run_command returns promptly on timeout.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.process_kill import kill_process_tree


def _alive(pid: int) -> bool:
    if os.name == "nt":
        r = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"],
            capture_output=True, text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return str(pid) in r.stdout and "No tasks" not in r.stdout
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def test_kill_process_tree_kills_descendants(tmp_path):
    child_pid_file = str(tmp_path / "child.pid").replace("\\", "/")
    child_script = (
        "import time,os;"
        f"open({child_pid_file!r},'w').write(str(os.getpid()));"
        "time.sleep(60)"
    )
    parent_script = (
        "import subprocess,sys,time;"
        f"subprocess.Popen([sys.executable,'-c',{child_script!r}]);"
        "time.sleep(60)"
    )
    parent = subprocess.Popen(
        [sys.executable, "-c", parent_script], start_new_session=True,
    )
    child_pid = None
    for _ in range(100):
        if Path(child_pid_file).exists():
            child_pid = int(Path(child_pid_file).read_text(encoding="utf-8").strip())
            break
        time.sleep(0.1)
    assert child_pid is not None, "grandchild did not start"

    kill_process_tree(parent.pid)

    # Windows keeps a zombie until the Popen handle is reaped; poll() releases it.
    deadline = time.time() + 5
    while time.time() < deadline:
        if parent.poll() is not None and not _alive(child_pid):
            break
        time.sleep(0.1)
    assert parent.poll() is not None, "parent still alive after kill_process_tree"
    assert not _alive(child_pid), "grandchild still alive after kill_process_tree"


def test_run_command_timeout_returns_promptly_with_grandchild(tmp_path):
    import src.tools.builtin.run_command as rc

    # The direct child spawns a grandchild that inherits the stdout pipe and
    # sleeps long past the timeout; killing only the direct child would leave
    # the pipe open and hang the call.
    spawn = tmp_path / "spawn.py"
    spawn.write_text(
        "import subprocess, sys, time\n"
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        "print('started', flush=True)\n",
        encoding="utf-8",
    )
    command = f'"{sys.executable}" "{spawn}"'
    shell = "cmd" if os.name == "nt" else "bash"

    start = time.time()
    result = asyncio.run(
        rc.RunCommandTool().execute(command, shell=shell, timeout=2)
    )
    elapsed = time.time() - start

    assert "timed out" in str(result).lower(), f"unexpected result: {result!r}"
    assert elapsed < 20, f"timeout did not return promptly: {elapsed:.1f}s"

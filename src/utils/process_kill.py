"""Kill a process and its whole descendant tree.

run_command/process spawn shells (powershell, cmd, bash) that in turn spawn
grandchildren (npx -> node, npm, etc.). Killing only the direct child leaves
grandchildren holding the stdout/stderr pipe write end, so the reader never
sees EOF and the coroutine hangs forever. These helpers kill the tree.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess

logger = logging.getLogger(__name__)


def kill_process_tree(pid: int) -> None:
    """Terminate pid and every descendant. Best-effort; never raises."""
    if not pid or pid <= 0:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                timeout=15,
            )
        else:
            try:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            except ProcessLookupError:
                os.kill(pid, signal.SIGKILL)
    except Exception as e:
        logger.warning(f"kill_process_tree({pid}) failed: {e}")

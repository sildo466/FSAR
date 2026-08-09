from __future__ import annotations

import os
import shutil
import stat
import subprocess
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).parent.parent


def _bash_executable() -> str:
    candidates = [
        Path(r"C:\Program Files\Git\bin\bash.exe"),
        Path(r"C:\Program Files\Git\usr\bin\bash.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    executable = shutil.which("bash")
    if executable:
        return executable
    pytest.skip("bash is not available")


def test_backend_xterm_receives_executable_and_argv_separately(tmp_path: Path):
    project_root = tmp_path / "project"
    scripts_dir = project_root / "scripts"
    scripts_dir.mkdir(parents=True)
    script = scripts_dir / "_backend.sh"
    shutil.copy2(ROOT / "scripts" / "_backend.sh", script)
    script.chmod(script.stat().st_mode | stat.S_IXUSR)

    controls = tmp_path / "controls.sh"
    controls.write_text(
        "uname() { printf 'Linux\\n'; }\n"
        "setsid() { \"$@\"; }\n"
        "xterm() {\n"
        "    : > .launcher-argv\n"
        "    for arg in \"$@\"; do printf '%s\\n' \"$arg\" >> .launcher-argv; done\n"
        "}\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            _bash_executable(),
            "-c",
            'source "$1"; source "$2" python3',
            "launcher-test",
            controls.as_posix(),
            script.as_posix(),
        ],
        cwd=project_root,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr

    capture = project_root / ".launcher-argv"
    deadline = time.monotonic() + 2
    while not capture.exists() and time.monotonic() < deadline:
        time.sleep(0.01)

    assert capture.exists()
    argv = capture.read_text(encoding="utf-8").splitlines()
    assert argv[:5] == ["-title", "FSAR Backend", "-e", "bash", "-c"]
    assert len(argv) == 6

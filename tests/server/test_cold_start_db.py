from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_cold_start_uses_initialized_home_database(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    fsar_home = tmp_path / "home"
    env = os.environ.copy()
    env["FSAR_HOME"] = str(fsar_home)
    env.pop("FSAR_CONFIG_PATH", None)
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(root), env.get("PYTHONPATH", "")) if part
    )
    expected_db = fsar_home / "data" / "memory.db"
    expected_config = fsar_home / "config" / "fsar.yaml"
    script = f"""
from pathlib import Path
from src.server import ws_server

engine = ws_server._engine
assert Path({str(expected_config)!r}).exists()
assert engine.session_store._db_path == Path({str(expected_db)!r})
conversation_id = engine.new_conversation()
assert engine.session_store.get_recent_messages(conversation_id) == []
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr

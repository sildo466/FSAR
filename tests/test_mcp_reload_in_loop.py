"""Verify /mcp reload works when called from inside the running event loop.

Reproduces the bug: `asyncio.run()` cannot be called from a running loop.
After the fix, `_cmd_mcp` is async and `await self.mcp.reload()` works.

Run:  python tests/test_mcp_reload_in_loop.py
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Snapshot user's real .env and replace with our temp version
real_env = ROOT / ".env"
backup_path = ROOT / ".env.reload_test_backup"


def main() -> int:
    if real_env.is_file():
        real_env.replace(backup_path)
    cwd = os.getcwd()
    os.chdir(str(ROOT))
    try:
        from main import FSAR

        # Force-set MCP_SERVERS AFTER import — main.py transitively imports
        # src.utils.config which calls load_dotenv() and re-populates from
        # whatever real_env currently contains. We override that with our
        # test value AFTER the imports.
        env_content = (
            "MCP_SERVERS='[{\"name\":\"alpha\",\"command\":\""
            + sys.executable.replace("\\", "/")
            + "\",\"args\":[\"" + str((ROOT / "tests" / "mcp_mock_server.py").resolve()).replace("\\", "/")
            + "\"],\"risk_level\":\"LOW\",\"enabled\":true}]'\n"
        )
        real_env.write_text(env_content, encoding="utf-8")
        os.environ["MCP_SERVERS"] = env_content.split("=", 1)[1].rstrip()

        async def go():
            fsar = FSAR()
            # Start MCP servers first (mimics what _main() does).
            await fsar.mcp.start()
            print(f"  post-start servers: {fsar.mcp.servers}")
            assert "alpha" in fsar.mcp.servers, "alpha should be started"

            # Reproduce the bug path: call _cmd_mcp reload from inside a loop.
            # Pre-fix this would raise "asyncio.run() cannot be called from
            # a running event loop".
            print("  calling _cmd_mcp('reload') from inside event loop...")
            await fsar._cmd_mcp("reload")
            print(f"  post-reload servers: {fsar.mcp.servers}")
            assert "alpha" in fsar.mcp.servers, "alpha should be present after reload"
            assert fsar.mcp.servers[0] in fsar.mcp._started and fsar.mcp._started[fsar.mcp.servers[0]], \
                "alpha should be started after reload"

            # Also verify the related subcommands still work
            await fsar._cmd_mcp("status")
            print("  OK: status also works inside loop")

            await fsar.mcp.stop()

        try:
            asyncio.run(go())
            print("\nOK: /mcp reload works inside the event loop")
            return 0
        except RuntimeError as e:
            if "asyncio.run()" in str(e) and "running event loop" in str(e):
                print(f"FAIL: bug regression — {e}")
                return 1
            raise
    finally:
        os.chdir(cwd)
        if backup_path.is_file():
            backup_path.replace(real_env)
        elif real_env.is_file():
            real_env.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
"""In-process smoke test for /mcp add and /mcp remove handlers.

Instantiates FSAR (without the event loop), calls _mcp_add_interactive
and _mcp_remove_interactive directly, verifies .env was written correctly.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Backup real .env if any
real_env = ROOT / ".env"
backup_path = ROOT / ".env.insar_test_backup"


def main() -> int:
    # Backup user .env to avoid clobbering
    if real_env.is_file():
        real_env.replace(backup_path)

    try:
        # Run FSAR init but skip the main loop
        from main import FSAR
        from src.mcp import cli as mcpcli

        # Save / restore cwd
        cwd = os.getcwd()
        # We want cwd to be ROOT so _find_env_file picks ROOT/.env
        os.chdir(str(ROOT))
        try:
            # Wipe .env if any leftover from a previous run
            real_env.unlink(missing_ok=True)

            fsar = FSAR()
            try:
                # --- /mcp add filesystem ---
                add_cmd = (
                    "filesystem --command npx "
                    "--args '[\"-y\", \"@modelcontextprotocol/server-filesystem\", \"C:/Users/TANG\"]' "
                    "--risk MEDIUM"
                )
                fsar._mcp_add_interactive(add_cmd)
                if not real_env.is_file():
                    print("[insar-test] FAIL: .env not created")
                    return 1
                servers = mcpcli._read_servers(real_env)
                if not servers or servers[0]["name"] != "filesystem":
                    print(f"[insar-test] FAIL: filesystem not added, got: {servers}")
                    return 1
                fs = servers[0]
                if fs.get("risk_level") != "MEDIUM":
                    print(f"[insar-test] FAIL: risk wrong: {fs}")
                    return 1
                if fs.get("args") != ["-y", "@modelcontextprotocol/server-filesystem", "C:/Users/TANG"]:
                    print(f"[insar-test] FAIL: args wrong: {fs.get('args')}")
                    return 1
                print("[insar-test] OK: /mcp add added filesystem")

                # --- /mcp add another server ---
                add_cmd2 = "everything --command npx --args '[\"-y\",\"@modelcontextprotocol/server-everything\"]' --risk LOW"
                fsar._mcp_add_interactive(add_cmd2)
                servers = mcpcli._read_servers(real_env)
                if len(servers) != 2:
                    print(f"[insar-test] FAIL: expected 2 servers, got {len(servers)}")
                    return 1
                print(f"[insar-test] OK: /mcp add appended everything (total {len(servers)})")

                # --- /mcp list ---
                print("[insar-test] listing via _mcp_list_interactive():")
                fsar._mcp_list_interactive()

                # --- /mcp remove ---
                fsar._mcp_remove_interactive("filesystem")
                servers = mcpcli._read_servers(real_env)
                if len(servers) != 1 or servers[0]["name"] != "everything":
                    print(f"[insar-test] FAIL: remove failed, got: {servers}")
                    return 1
                print("[insar-test] OK: /mcp remove deleted filesystem")

                # --- /mcp remove last ---
                fsar._mcp_remove_interactive("everything")
                if mcpcli.parse_env_var(real_env, "MCP_SERVERS") is not None:
                    print(f"[insar-test] FAIL: MCP_SERVERS line should be gone")
                    return 1
                print("[insar-test] OK: /mcp remove last entry dropped MCP_SERVERS line")

                # --- /mcp snippet via add --snippet ---
                add_snip = "cua --command cua-mcp-server --risk HIGH --snippet"
                fsar._mcp_add_interactive(add_snip)
                # Snippet should NOT have written anything
                if mcpcli.parse_env_var(real_env, "MCP_SERVERS") is not None:
                    print(f"[insar-test] FAIL: --snippet wrote to .env")
                    return 1
                print("[insar-test] OK: /mcp add --snippet printed without writing")

                print("[insar-test] all OK")
            finally:
                # Clean up MCPManager resources
                try:
                    asyncio.run(fsar.mcp.stop())
                except Exception:
                    pass
        finally:
            os.chdir(cwd)
    finally:
        # Restore user .env
        if backup_path.is_file():
            backup_path.replace(real_env)
        elif real_env.is_file():
            real_env.unlink(missing_ok=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
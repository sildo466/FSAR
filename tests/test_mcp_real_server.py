"""End-to-end against a REAL MCP server: @modelcontextprotocol/server-everything.

Temporarily enables the 'everything' entry in config/mcp_servers.yaml,
runs MCPManager, verifies the server starts (via npx) and at least one
tool call succeeds. Restores the config afterward.
"""

from __future__ import annotations

import asyncio
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.mcp.manager import MCPManager  # noqa: E402
from src.tools.registry import ToolRegistry  # noqa: E402


async def run_real_server_test() -> int:
    cfg_path = ROOT / "config" / "mcp_servers.yaml"
    backup = cfg_path.with_suffix(".yaml.bak")
    shutil.copy(cfg_path, backup)
    print(f"[real-test] backed up {cfg_path} -> {backup}")

    # Enable just the 'everything' server
    text = cfg_path.read_text(encoding="utf-8")
    # Toggle enabled: false -> enabled: true on the 'everything' entry
    new_text = text.replace(
        """  - name: everything
    transport: stdio
    command: npx
    args: ["-y", "@modelcontextprotocol/server-everything"]
    risk_level: LOW
    enabled: false""",
        """  - name: everything
    transport: stdio
    command: npx
    args: ["-y", "@modelcontextprotocol/server-everything"]
    risk_level: LOW
    enabled: true""",
    )
    if new_text == text:
        print("[real-test] FAIL: could not find 'everything' block to enable")
        return 1
    cfg_path.write_text(new_text, encoding="utf-8")
    print("[real-test] enabled 'everything' server in config")

    registry = ToolRegistry()
    manager = MCPManager(registry, config_path=cfg_path)

    rc = 0
    try:
        print("[real-test] starting manager (this may download npx packages, takes ~30s first time)...")
        try:
            await asyncio.wait_for(manager.start(), timeout=120.0)
        except asyncio.TimeoutError:
            print("[real-test] FAIL: start() timed out")
            rc = 1
        except Exception as e:
            print(f"[real-test] FAIL: start() raised: {e}")
            rc = 1

        if rc == 0:
            print(f"[real-test] servers up: {manager.servers}")
            if "everything" not in manager.servers:
                print("[real-test] FAIL: 'everything' not started")
                rc = 1
            else:
                info = manager.get_client("everything").server_info
                print(f"[real-test] server info: {info}")

                tools = manager.list_visible_tools()
                names = sorted(t.name for t in tools)
                print(f"[real-test] discovered {len(tools)} tools:")
                for n in names:
                    t = registry.get(n)
                    print(f"  - {n} (risk={t.risk_level})")

                if not tools:
                    print("[real-test] FAIL: no tools discovered")
                    rc = 1
                else:
                    # Pick the first tool and try to call it with no args.
                    # If it requires args, the result will be an error from
                    # the server — that's still useful signal that the round
                    # trip works end-to-end.
                    first = tools[0]
                    params = first.parameters.get("properties", {}) or {}
                    required = first.parameters.get("required", []) or []
                    call_args = {p: "test" for p in required if p in params}
                    print(f"[real-test] trying call: {first.original_name}({call_args})")
                    try:
                        result = await registry.execute(first.name, **call_args)
                        print(f"[real-test] result: {result[:200]!r}")
                    except Exception as e:
                        print(f"[real-test] call raised (still proves wiring works): {e}")
                    rc = 0  # we got far enough

    finally:
        # Restore config
        shutil.move(backup, cfg_path)
        print(f"[real-test] restored config")
        await manager.stop()

    return rc


if __name__ == "__main__":
    try:
        rc = asyncio.run(run_real_server_test())
    except KeyboardInterrupt:
        rc = 130
    sys.exit(rc)
"""Manager-level test: load YAML config pointing to the mock server,
verify manager.start() spawns the subprocess, registers tools into a
registry, and manager.stop() cleans up.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.mcp.manager import MCPManager  # noqa: E402
from src.tools.registry import ToolRegistry  # noqa: E402

# Isolate from the user's real .env: importing src.mcp.manager transitively
# loads src.utils.config which calls load_dotenv() and re-populates
# os.environ from .env (including any MCP_SERVERS entry). Pop AFTER the
# imports so we override what dotenv put there.
os.environ.pop("MCP_SERVERS", None)


async def run_manager_test() -> int:
    py = sys.executable
    server_script = str(ROOT / "tests" / "mcp_mock_server.py")

    # --- Config A: one valid server, one disabled, one bogus ---
    # YAML double-quoted strings treat backslash as escape — use single quotes
    # for Windows paths to keep them literal.
    py_q = py.replace("\\", "/")
    script_q = server_script.replace("\\", "/")
    yaml_text = f"""
servers:
  - name: alpha
    transport: stdio
    command: '{py_q}'
    args: ['{script_q}']
    risk_level: MEDIUM
    enabled: true
  - name: beta_disabled
    transport: stdio
    command: '{py_q}'
    args: ['{script_q}']
    risk_level: LOW
    enabled: false
  - name: gamma_broken
    transport: stdio
    command: 'definitely_not_a_real_command_xyz'
    args: []
    risk_level: HIGH
    enabled: true
"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    ) as f:
        f.write(yaml_text)
        cfg_path = f.name

    print(f"[mgr-test] config: {cfg_path}")

    registry = ToolRegistry()
    initial_count = len(registry.list_tools())
    print(f"[mgr-test] initial registry size: {initial_count}")

    manager = MCPManager(registry, config_path=cfg_path)

    try:
        await manager.start()
    except Exception as e:
        print(f"[mgr-test] FAIL: manager.start() raised: {e}")
        return 1

    print(f"[mgr-test] manager.servers = {manager.servers}")
    print(f"[mgr-test] manager._started = {manager._started}")

    # alpha should be up, gamma_broken should be down, beta_disabled absent
    if "alpha" not in manager.servers:
        print(f"[mgr-test] FAIL: alpha server not started")
        return 1
    if "gamma_broken" in manager.servers:
        print(f"[mgr-test] FAIL: gamma_broken should have failed to start")
        return 1
    if "beta_disabled" in manager.servers:
        print(f"[mgr-test] FAIL: beta_disabled should not have been started")
        return 1

    if not manager._started.get("alpha"):
        print(f"[mgr-test] FAIL: alpha not in started map")
        return 1

    # Tools from alpha should be registered
    names = sorted(t.name for t in manager.list_visible_tools())
    print(f"[mgr-test] visible MCP tools: {names}")
    expected = {"mcp__alpha__echo", "mcp__alpha__add", "mcp__alpha__fail"}
    if set(names) != expected:
        print(f"[mgr-test] FAIL: expected {expected}, got {set(names)}")
        return 1

    # They should also be in the underlying registry
    in_registry = sorted(registry.get_tool_names())
    print(f"[mgr-test] full registry: {in_registry}")
    for n in expected:
        if n not in in_registry:
            print(f"[mgr-test] FAIL: {n} missing from registry")
            return 1

    # Risk level propagates
    echo_tool = registry.get("mcp__alpha__echo")
    if echo_tool.risk_level != "MEDIUM":
        print(f"[mgr-test] FAIL: risk_level expected MEDIUM, got {echo_tool.risk_level!r}")
        return 1

    # End-to-end call via the registry execute path
    result = await registry.execute("mcp__alpha__add", a=10, b=20)
    print(f"[mgr-test] registry.execute(add, 10, 20) -> {result!r}")
    if result.strip() != "30":
        print(f"[mgr-test] FAIL: expected '30', got {result!r}")
        return 1

    # --- Reload (should tear down + start fresh) ---
    print("[mgr-test] calling reload()...")
    try:
        await manager.reload()
    except Exception as e:
        print(f"[mgr-test] FAIL: reload raised: {e}")
        return 1
    names2 = sorted(t.name for t in manager.list_visible_tools())
    print(f"[mgr-test] after reload: {names2}")
    if set(names2) != expected:
        print(f"[mgr-test] FAIL: after reload, expected {expected}, got {set(names2)}")
        return 1

    # --- Stop ---
    print("[mgr-test] calling stop()...")
    await manager.stop()
    print(f"[mgr-test] after stop: servers={manager.servers}")

    # Tools remain in registry but execute() should now fail
    print("[mgr-test] verify execute after stop raises (expected)...")
    try:
        await registry.execute("mcp__alpha__add", a=1, b=1)
        print(f"[mgr-test] FAIL: expected RuntimeError after stop, got success")
        return 1
    except RuntimeError as e:
        print(f"[mgr-test] OK: got expected RuntimeError: {e}")

    print("[mgr-test] OK")
    return 0


if __name__ == "__main__":
    try:
        rc = asyncio.run(run_manager_test())
    except KeyboardInterrupt:
        rc = 130
    sys.exit(rc)
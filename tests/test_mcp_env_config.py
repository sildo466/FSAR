"""Tests for MCP config loading: env (MCP_SERVERS) vs YAML fallback.

Verifies:
    1. Env var with valid JSON loads correctly
    2. Env takes precedence over YAML when both are set
    3. Empty/unset env falls back to YAML
    4. Invalid JSON in env is logged and falls back to YAML
    5. Env non-array value (e.g. dict) is rejected
    6. End-to-end: env-configured server actually starts via subprocess

Run:  python tests/test_mcp_env_config.py
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

# Load .env first so we have a known state, then override per-test
from src.utils.config import get_config  # noqa: E402
get_config()  # triggers dotenv load

from src.mcp.manager import MCPManager  # noqa: E402
from src.tools.registry import ToolRegistry  # noqa: E402


SERVER_SCRIPT = str(ROOT / "tests" / "mcp_mock_server.py")
PY = sys.executable


def _env_for_test(servers: list[dict]) -> str:
    return json.dumps(servers)


async def test_env_only() -> bool:
    """Env var set, YAML file absent → env path used."""
    print("\n[env-test 1] env only, no YAML")
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=True) as f:
        bogus_path = f.name  # file exists but empty
        Path(bogus_path).unlink(missing_ok=True)  # make it actually absent

        env_value = _env_for_test([
            {"name": "alpha", "command": PY, "args": [SERVER_SCRIPT],
             "risk_level": "LOW", "enabled": True},
            {"name": "beta_disabled", "command": PY, "args": [SERVER_SCRIPT],
             "risk_level": "MEDIUM", "enabled": False},
        ])
        os.environ["MCP_SERVERS"] = env_value

        try:
            registry = ToolRegistry()
            manager = MCPManager(registry, config_path=bogus_path)
            await manager.start()
            print(f"  servers: {manager.servers}")
            assert manager.servers == ["alpha"], f"expected ['alpha'], got {manager.servers}"
            tools = manager.list_visible_tools()
            assert len(tools) == 3, f"expected 3 tools from alpha, got {len(tools)}"
            for t in tools:
                assert t.risk_level == "LOW", f"risk should be LOW, got {t.risk_level}"
            print(f"  OK: env-only path produced {len(tools)} tools")
            await manager.stop()
            return True
        finally:
            os.environ.pop("MCP_SERVERS", None)


async def test_env_overrides_yaml() -> bool:
    """Both env and YAML present → env wins."""
    print("\n[env-test 2] env + YAML, env wins")
    yaml_text = f"""
servers:
  - name: from_yaml
    transport: stdio
    command: '{PY}'
    args: ['{SERVER_SCRIPT}']
    risk_level: HIGH
    enabled: true
"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    ) as f:
        f.write(yaml_text)
        yaml_path = f.name

    os.environ["MCP_SERVERS"] = _env_for_test([
        {"name": "from_env", "command": PY, "args": [SERVER_SCRIPT],
         "risk_level": "MEDIUM", "enabled": True},
    ])

    try:
        registry = ToolRegistry()
        manager = MCPManager(registry, config_path=yaml_path)
        await manager.start()
        print(f"  servers: {manager.servers}")
        assert manager.servers == ["from_env"], (
            f"env should override yaml, got {manager.servers}"
        )
        tool = registry.get("mcp__from_env__echo")
        assert tool is not None, "mcp__from_env__echo should be registered"
        assert tool.risk_level == "MEDIUM", f"expected MEDIUM, got {tool.risk_level}"
        print(f"  OK: env overrode yaml (from_env with risk=MEDIUM)")
        await manager.stop()
        Path(yaml_path).unlink(missing_ok=True)
        return True
    finally:
        os.environ.pop("MCP_SERVERS", None)


async def test_yaml_fallback() -> bool:
    """Env unset, YAML present → YAML path used."""
    print("\n[env-test 3] env unset, YAML fallback")
    yaml_text = f"""
servers:
  - name: yaml_only
    transport: stdio
    command: '{PY}'
    args: ['{SERVER_SCRIPT}']
    risk_level: LOW
    enabled: true
"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    ) as f:
        f.write(yaml_text)
        yaml_path = f.name

    os.environ.pop("MCP_SERVERS", None)

    try:
        registry = ToolRegistry()
        manager = MCPManager(registry, config_path=yaml_path)
        await manager.start()
        print(f"  servers: {manager.servers}")
        assert manager.servers == ["yaml_only"], (
            f"YAML fallback should yield yaml_only, got {manager.servers}"
        )
        print(f"  OK: YAML fallback worked")
        await manager.stop()
        Path(yaml_path).unlink(missing_ok=True)
        return True
    finally:
        os.environ.pop("MCP_SERVERS", None)


async def test_invalid_json_falls_back() -> bool:
    """Env holds garbage → manager logs error and falls back to YAML."""
    print("\n[env-test 4] invalid JSON in env, falls back to YAML")
    yaml_text = f"""
servers:
  - name: yaml_recovered
    transport: stdio
    command: '{PY}'
    args: ['{SERVER_SCRIPT}']
    risk_level: LOW
    enabled: true
"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    ) as f:
        f.write(yaml_text)
        yaml_path = f.name

    os.environ["MCP_SERVERS"] = "not valid json {"

    try:
        registry = ToolRegistry()
        manager = MCPManager(registry, config_path=yaml_path)
        await manager.start()
        print(f"  servers: {manager.servers}")
        assert manager.servers == ["yaml_recovered"], (
            f"expected fallback to yaml_recovered, got {manager.servers}"
        )
        print(f"  OK: invalid env JSON didn't crash, YAML recovered it")
        await manager.stop()
        Path(yaml_path).unlink(missing_ok=True)
        return True
    finally:
        os.environ.pop("MCP_SERVERS", None)


async def test_env_non_array_rejected() -> bool:
    """Env holds valid JSON but not an array → reject, fall back."""
    print("\n[env-test 5] env JSON is dict (not array), rejected")
    yaml_text = f"""
servers:
  - name: yaml_again
    transport: stdio
    command: '{PY}'
    args: ['{SERVER_SCRIPT}']
    risk_level: LOW
    enabled: true
"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    ) as f:
        f.write(yaml_text)
        yaml_path = f.name

    os.environ["MCP_SERVERS"] = '{"name":"not_an_array","command":"x"}'

    try:
        registry = ToolRegistry()
        manager = MCPManager(registry, config_path=yaml_path)
        await manager.start()
        print(f"  servers: {manager.servers}")
        assert manager.servers == ["yaml_again"], (
            f"non-array env should be rejected, got {manager.servers}"
        )
        print(f"  OK: non-array env rejected, YAML fallback worked")
        await manager.stop()
        Path(yaml_path).unlink(missing_ok=True)
        return True
    finally:
        os.environ.pop("MCP_SERVERS", None)


async def main() -> int:
    results = []
    for test in [
        test_env_only,
        test_env_overrides_yaml,
        test_yaml_fallback,
        test_invalid_json_falls_back,
        test_env_non_array_rejected,
    ]:
        try:
            ok = await test()
            results.append((test.__name__, ok))
        except Exception as e:
            print(f"  FAIL: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            results.append((test.__name__, False))

    print("\n=== summary ===")
    for name, ok in results:
        print(f"  {'OK' if ok else 'FAIL'}  {name}")

    failed = sum(1 for _, ok in results if not ok)
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        rc = asyncio.run(main())
    except KeyboardInterrupt:
        rc = 130
    sys.exit(rc)
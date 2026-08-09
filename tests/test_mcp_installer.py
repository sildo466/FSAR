"""Test the in-FSAR /mcp install interactive flow.

Simulates user input via stdin monkey-patching, calls
_mcp_install_interactive, verifies .env was written correctly.

Run:  python tests/test_mcp_installer.py
"""

from __future__ import annotations

import builtins
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

real_env = ROOT / ".env"
backup_path = ROOT / ".env.installer_test_backup"


def with_stdin(lines: list[str]):
    """Replace input() with a generator that yields from `lines`."""
    lines_iter = iter(lines)
    orig_input = builtins.input

    def fake_input(prompt=""):
        try:
            val = next(lines_iter)
        except StopIteration:
            raise EOFError
        print(f"{prompt}{val}")  # echo for visibility
        return val

    builtins.input = fake_input
    return lambda: setattr(builtins, "input", orig_input)


def fresh_env() -> Path:
    f = open(real_env, "w", encoding="utf-8")
    f.close()
    return real_env


def read_servers() -> list[dict]:
    from src.mcp import cli as mcpcli
    parsed = mcpcli.parse_env_var(real_env, "MCP_SERVERS")
    if not parsed:
        return []
    raw = mcpcli._strip_surrounding_quotes(parsed[2])
    return json.loads(raw)


def run_tests() -> int:
    # Backup real .env if any
    if real_env.is_file():
        real_env.replace(backup_path)

    cwd = os.getcwd()
    os.chdir(str(ROOT))
    results = []

    try:
        from main import FSAR

        # === test 1: install preset with no placeholders ===
        print("\n[installer-test 1] install everything preset (no placeholders)")
        fresh_env()
        fsar = FSAR()
        try:
            restore = with_stdin([])  # no interactive prompts needed
            try:
                fsar._mcp_install_interactive("everything")
            finally:
                restore()
            servers = read_servers()
            if not servers or servers[0]["name"] != "everything":
                print(f"  FAIL: got {servers}")
                results.append(False)
            else:
                ev = servers[0]
                if ev.get("risk_level") != "LOW":
                    print(f"  FAIL: risk wrong: {ev}")
                    results.append(False)
                elif ev.get("args") != ["-y", "@modelcontextprotocol/server-everything"]:
                    print(f"  FAIL: args wrong: {ev.get('args')}")
                    results.append(False)
                elif ev.get("command") != "npx":
                    print(f"  FAIL: command wrong: {ev}")
                    results.append(False)
                else:
                    print(f"  OK: installed everything")
                    results.append(True)
        finally:
            try:
                import asyncio
                asyncio.run(fsar.mcp.stop())
            except Exception:
                pass

        # === test 2: install preset WITH placeholder, value via CLI flag ===
        print("\n[installer-test 2] install filesystem with --path flag")
        fresh_env()
        fsar = FSAR()
        try:
            # No stdin needed — placeholder supplied as flag
            fsar._mcp_install_interactive("filesystem --path C:/test_data")
            servers = read_servers()
            if not servers or servers[0]["name"] != "filesystem":
                print(f"  FAIL: got {servers}")
                results.append(False)
            else:
                fs = servers[0]
                if "C:/test_data" not in fs.get("args", []):
                    print(f"  FAIL: placeholder not filled: {fs.get('args')}")
                    results.append(False)
                elif fs.get("risk_level") != "MEDIUM":
                    print(f"  FAIL: risk wrong: {fs}")
                    results.append(False)
                else:
                    print(f"  OK: installed filesystem with --path C:/test_data")
                    results.append(True)
        finally:
            try:
                import asyncio
                asyncio.run(fsar.mcp.stop())
            except Exception:
                pass

        # === test 3: install preset WITH placeholder, value via stdin ===
        print("\n[installer-test 3] install filesystem, prompt user for path")
        fresh_env()
        fsar = FSAR()
        try:
            # input() returns 'D:/my_stuff' for the placeholder
            restore = with_stdin(["D:/my_stuff"])
            try:
                fsar._mcp_install_interactive("filesystem")
            finally:
                restore()
            servers = read_servers()
            if not servers or servers[0]["name"] != "filesystem":
                print(f"  FAIL: got {servers}")
                results.append(False)
            else:
                if "D:/my_stuff" not in servers[0].get("args", []):
                    print(f"  FAIL: prompt answer not used: {servers[0]}")
                    results.append(False)
                else:
                    print(f"  OK: prompt answer filled placeholder")
                    results.append(True)
        finally:
            try:
                import asyncio
                asyncio.run(fsar.mcp.stop())
            except Exception:
                pass

        # === test 4: custom server via interactive prompts ===
        print("\n[installer-test 4] install custom server via prompts")
        fresh_env()
        fsar = FSAR()
        try:
            # Catalog picks 'c' (custom), then name/command/args/risk
            restore = with_stdin([
                "c",                     # catalog choice: custom
                "my-cua",                # name
                "cua-mcp-server",        # command
                "",                      # args (empty)
                "MEDIUM",                # risk
            ])
            try:
                fsar._mcp_install_interactive("")
            finally:
                restore()
            servers = read_servers()
            if not servers or servers[0]["name"] != "my-cua":
                print(f"  FAIL: got {servers}")
                results.append(False)
            else:
                cu = servers[0]
                if cu.get("command") != "cua-mcp-server":
                    print(f"  FAIL: command wrong: {cu}")
                    results.append(False)
                elif cu.get("risk_level") != "MEDIUM":
                    print(f"  FAIL: risk wrong: {cu}")
                    results.append(False)
                else:
                    print(f"  OK: custom install worked")
                    results.append(True)
        finally:
            try:
                import asyncio
                asyncio.run(fsar.mcp.stop())
            except Exception:
                pass

        # === test 5: idempotent re-install (updates existing entry) ===
        print("\n[installer-test 5] re-install same name updates entry")
        fresh_env()
        fsar = FSAR()
        try:
            fsar._mcp_install_interactive("everything")
            fsar._mcp_install_interactive("filesystem --path C:/dup")
            fsar._mcp_install_interactive("everything")  # re-install
            servers = read_servers()
            names = [s["name"] for s in servers]
            if names.count("everything") != 1:
                print(f"  FAIL: duplicate 'everything', got {names}")
                results.append(False)
            elif len(servers) != 2:
                print(f"  FAIL: expected 2 unique servers, got {len(servers)}: {names}")
                results.append(False)
            else:
                print(f"  OK: re-install updated without duplicating")
                results.append(True)
        finally:
            try:
                import asyncio
                asyncio.run(fsar.mcp.stop())
            except Exception:
                pass

        # === test 6: catalog display ===
        print("\n[installer-test 6] catalog shows all presets")
        fsar = FSAR()
        fsar._mcp_show_catalog()
        from src.mcp.presets import MCP_PRESETS
        for key in MCP_PRESETS:
            # Just verify it doesn't crash
            pass
        print(f"  OK: catalog rendered ({len(MCP_PRESETS)} presets)")
        results.append(True)

        # === test 7: cancel on empty input ===
        print("\n[installer-test 7] cancel with empty input")
        fresh_env()
        fsar = FSAR()
        try:
            restore = with_stdin([""])
            try:
                fsar._mcp_install_interactive("")
            finally:
                restore()
            servers = read_servers()
            if servers:
                print(f"  FAIL: cancel should not write: {servers}")
                results.append(False)
            else:
                print(f"  OK: cancel did not write")
                results.append(True)
        finally:
            try:
                import asyncio
                asyncio.run(fsar.mcp.stop())
            except Exception:
                pass

        # === test 8: unknown preset name ===
        print("\n[installer-test 8] unknown preset name rejected")
        fresh_env()
        fsar = FSAR()
        try:
            fsar._mcp_install_interactive("nonexistent-server-xyz")
            servers = read_servers()
            if servers:
                print(f"  FAIL: should not write for unknown preset: {servers}")
                results.append(False)
            else:
                print(f"  OK: unknown preset rejected")
                results.append(True)
        finally:
            try:
                import asyncio
                asyncio.run(fsar.mcp.stop())
            except Exception:
                pass

    finally:
        os.chdir(cwd)
        # Restore user .env
        if backup_path.is_file():
            backup_path.replace(real_env)
        elif real_env.is_file():
            real_env.unlink(missing_ok=True)

    print("\n=== summary ===")
    passed = sum(1 for r in results if r)
    failed = len(results) - passed
    for i, ok in enumerate(results, 1):
        print(f"  {'OK' if ok else 'FAIL'}  test {i}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run_tests())
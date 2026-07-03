"""Tests for src.mcp.cli — add / remove / list / snippet.

Run:  python tests/test_mcp_cli.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.mcp import cli as mcpcli  # noqa: E402


def read_servers(env_path: Path) -> list[dict]:
    """Read MCP_SERVERS from an env file the same way the CLI does."""
    parsed = mcpcli.parse_env_var(env_path, "MCP_SERVERS")
    if not parsed:
        return []
    raw = parsed[2].strip()
    raw = mcpcli._strip_surrounding_quotes(raw)
    return json.loads(raw)


def run_cli(*args: str, env_file: str | None = None, env: dict | None = None) -> tuple[int, str, str]:
    """Invoke the CLI as a subprocess (cleaner than in-process — no env pollution)."""
    cmd = [sys.executable, "-m", "src.mcp.cli", *args]
    if env_file:
        cmd += ["--env-file", env_file]
    proc_env = os.environ.copy()
    proc_env.pop("MCP_SERVERS", None)
    if env:
        proc_env.update(env)
    proc = subprocess.run(
        cmd, capture_output=True, text=True, cwd=str(ROOT), env=proc_env,
        timeout=30, encoding="utf-8", errors="replace",
    )
    return proc.returncode, proc.stdout, proc.stderr


def fresh_env(content: str = "") -> Path:
    """Create a fresh .env file and return its path."""
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".env", delete=False, encoding="utf-8"
    )
    f.write(content)
    f.close()
    return Path(f.name)


# ===== tests =====

def test_add_to_empty_env() -> bool:
    print("\n[cli-test 1] add to empty .env")
    env = fresh_env("# top-level comment\nOTHER_VAR=hello\n")
    try:
        rc, out, err = run_cli(
            "add", "cua",
            "--command", "cua-mcp-server",
            "--risk", "HIGH",
            env_file=str(env),
        )
        if rc != 0:
            print(f"  FAIL: rc={rc} stderr={err}")
            return False
        text = env.read_text(encoding="utf-8")
        # Must preserve OTHER_VAR and the comment
        if "OTHER_VAR=hello" not in text:
            print(f"  FAIL: OTHER_VAR lost:\n{text}")
            return False
        if "# top-level comment" not in text:
            print(f"  FAIL: top-level comment lost:\n{text}")
            return False
        # Must contain MCP_SERVERS
        servers = read_servers(env)
        if not servers:
            print(f"  FAIL: MCP_SERVERS not parseable or empty")
            return False
        if len(servers) != 1 or servers[0]["name"] != "cua":
            print(f"  FAIL: wrong servers: {servers}")
            return False
        if servers[0]["command"] != "cua-mcp-server":
            print(f"  FAIL: wrong command: {servers[0]}")
            return False
        if servers[0]["risk_level"] != "HIGH":
            print(f"  FAIL: wrong risk: {servers[0]}")
            return False
        if servers[0]["enabled"] is not True:
            print(f"  FAIL: should default enabled=True: {servers[0]}")
            return False
        print(f"  OK: added cua, preserved comments + other vars")
        return True
    finally:
        env.unlink(missing_ok=True)


def test_add_with_args() -> bool:
    print("\n[cli-test 2] add with multiple args")
    env = fresh_env()
    try:
        rc, out, err = run_cli(
            "add", "filesystem",
            "--command", "npx",
            "--args", '["-y", "@modelcontextprotocol/server-filesystem", "C:/Users/TANG"]',
            "--risk", "MEDIUM",
            env_file=str(env),
        )
        if rc != 0:
            print(f"  FAIL: rc={rc} stderr={err}")
            return False
        parsed = mcpcli.parse_env_var(env, "MCP_SERVERS")
        if parsed is None:
            servers = []
        else:
            servers = read_servers(env)
        fs = servers[0]
        if fs["args"] != ["-y", "@modelcontextprotocol/server-filesystem", "C:/Users/TANG"]:
            print(f"  FAIL: args wrong: {fs['args']}")
            return False
        if fs["risk_level"] != "MEDIUM":
            print(f"  FAIL: risk wrong: {fs}")
            return False
        print(f"  OK: args and risk preserved")
        return True
    finally:
        env.unlink(missing_ok=True)


def test_add_replaces_existing() -> bool:
    print("\n[cli-test 3] add replaces existing entry with same name")
    env = fresh_env('MCP_SERVERS=\'{"name":"cua","command":"old-cmd","enabled":true}\'\n')
    try:
        rc, out, err = run_cli(
            "add", "cua",
            "--command", "new-cmd",
            "--risk", "MEDIUM",
            env_file=str(env),
        )
        if rc != 0:
            print(f"  FAIL: rc={rc} stderr={err}")
            return False
        parsed = mcpcli.parse_env_var(env, "MCP_SERVERS")
        if parsed is None:
            servers = []
        else:
            servers = read_servers(env)
        if len(servers) != 1:
            print(f"  FAIL: expected 1 server, got {len(servers)}")
            return False
        if servers[0]["command"] != "new-cmd":
            print(f"  FAIL: command not replaced: {servers[0]}")
            return False
        print(f"  OK: replaced existing entry")
        return True
    finally:
        env.unlink(missing_ok=True)


def test_add_appends_to_existing() -> bool:
    print("\n[cli-test 4] add appends when name doesn't exist")
    env = fresh_env('MCP_SERVERS=\'[{"name":"a","command":"cmd-a","enabled":true}]\'\n')
    try:
        rc, _, err = run_cli(
            "add", "b",
            "--command", "cmd-b",
            env_file=str(env),
        )
        if rc != 0:
            print(f"  FAIL: rc={rc} stderr={err}")
            return False
        parsed = mcpcli.parse_env_var(env, "MCP_SERVERS")
        if parsed is None:
            servers = []
        else:
            servers = read_servers(env)
        names = [s["name"] for s in servers]
        if names != ["a", "b"]:
            print(f"  FAIL: expected ['a','b'], got {names}")
            return False
        print(f"  OK: appended b after a")
        return True
    finally:
        env.unlink(missing_ok=True)


def test_remove() -> bool:
    print("\n[cli-test 5] remove entry")
    env = fresh_env(
        'MCP_SERVERS=\'[{"name":"a","command":"x","enabled":true},'
        '{"name":"b","command":"y","enabled":true}]\'\n'
    )
    try:
        rc, _, err = run_cli("remove", "a", env_file=str(env))
        if rc != 0:
            print(f"  FAIL: rc={rc} stderr={err}")
            return False
        parsed = mcpcli.parse_env_var(env, "MCP_SERVERS")
        if parsed is None:
            servers = []
        else:
            servers = read_servers(env)
        if [s["name"] for s in servers] != ["b"]:
            print(f"  FAIL: expected only b, got {servers}")
            return False
        print(f"  OK: removed a, b remains")
        return True
    finally:
        env.unlink(missing_ok=True)


def test_remove_last_drops_line() -> bool:
    print("\n[cli-test 6] remove last entry drops MCP_SERVERS line")
    env = fresh_env('MCP_SERVERS=\'[{"name":"only","command":"x","enabled":true}]\'\n')
    try:
        rc, _, err = run_cli("remove", "only", env_file=str(env))
        if rc != 0:
            print(f"  FAIL: rc={rc} stderr={err}")
            return False
        parsed = mcpcli.parse_env_var(env, "MCP_SERVERS")
        if parsed is not None:
            print(f"  FAIL: MCP_SERVERS line should be gone, got: {parsed[2]}")
            return False
        print(f"  OK: MCP_SERVERS line removed when last entry deleted")
        return True
    finally:
        env.unlink(missing_ok=True)


def test_remove_nonexistent() -> bool:
    print("\n[cli-test 7] remove nonexistent returns error")
    env = fresh_env('MCP_SERVERS=\'[{"name":"a","command":"x","enabled":true}]\'\n')
    try:
        rc, out, err = run_cli("remove", "ghost", env_file=str(env))
        if rc == 0:
            print(f"  FAIL: should have returned non-zero")
            return False
        if "ghost" not in (out + err):
            print(f"  FAIL: should mention 'ghost' in output: out={out!r} err={err!r}")
            return False
        print(f"  OK: returned rc={rc}, mentioned ghost")
        return True
    finally:
        env.unlink(missing_ok=True)


def test_list_shows_servers() -> bool:
    print("\n[cli-test 8] list shows configured servers")
    env = fresh_env(
        'MCP_SERVERS=\'[{"name":"alpha","command":"a-cmd","args":["x"],"risk_level":"LOW","enabled":true},'
        '{"name":"beta","command":"b-cmd","risk_level":"HIGH","enabled":false}]\'\n'
    )
    try:
        rc, out, err = run_cli("list", env_file=str(env))
        if rc != 0:
            print(f"  FAIL: rc={rc} stderr={err}")
            return False
        if "alpha" not in out or "beta" not in out:
            print(f"  FAIL: names missing from output:\n{out}")
            return False
        if "a-cmd" not in out or "b-cmd" not in out:
            print(f"  FAIL: commands missing:\n{out}")
            return False
        if "ON" not in out or "off" not in out:
            print(f"  FAIL: enabled flags missing:\n{out}")
            return False
        print(f"  OK: list output shows both servers with state")
        return True
    finally:
        env.unlink(missing_ok=True)


def test_multiline_preservation() -> bool:
    print("\n[cli-test 9] multi-line MCP_SERVERS survives edit")
    initial = (
        "# header comment\n"
        "OTHER=foo\n"
        "\n"
        "MCP_SERVERS=[\n"
        '  {"name":"a","command":"x","enabled":true}\n'
        "]\n"
        "\n"
        "TRAILING=yes\n"
    )
    env = fresh_env(initial)
    try:
        rc, _, err = run_cli("add", "b", "--command", "y", env_file=str(env))
        if rc != 0:
            print(f"  FAIL: rc={rc} stderr={err}")
            return False
        text = env.read_text(encoding="utf-8")
        if "OTHER=foo" not in text:
            print(f"  FAIL: OTHER lost")
            return False
        if "TRAILING=yes" not in text:
            print(f"  FAIL: TRAILING lost")
            return False
        if "# header comment" not in text:
            print(f"  FAIL: header comment lost")
            return False
        parsed = mcpcli.parse_env_var(env, "MCP_SERVERS")
        if parsed is None:
            servers = []
        else:
            servers = read_servers(env)
        if [s["name"] for s in servers] != ["a", "b"]:
            print(f"  FAIL: expected a+b, got {servers}")
            return False
        print(f"  OK: multi-line write preserves surrounding content")
        return True
    finally:
        env.unlink(missing_ok=True)


def test_snippet_prints_only() -> bool:
    print("\n[cli-test 10] snippet prints but doesn't touch .env")
    env = fresh_env()
    try:
        # snippet does NOT accept --env-file (it doesn't touch the file)
        rc, out, err = run_cli(
            "snippet", "cua",
            "--command", "cua-mcp-server",
            "--risk", "HIGH",
        )
        if rc != 0:
            print(f"  FAIL: rc={rc} stderr={err}")
            return False
        text = env.read_text(encoding="utf-8")
        if text.strip():
            print(f"  FAIL: snippet should not write to .env, got:\n{text}")
            return False
        snippet = json.loads(out.strip())
        if snippet.get("name") != "cua":
            print(f"  FAIL: snippet wrong: {snippet}")
            return False
        print(f"  OK: snippet printed {snippet}, file untouched")
        return True
    finally:
        env.unlink(missing_ok=True)


def test_dry_run_does_not_write() -> bool:
    print("\n[cli-test 11] dry-run doesn't write")
    env = fresh_env()
    try:
        rc, out, err = run_cli(
            "add", "cua",
            "--command", "cua-mcp-server",
            "--dry-run",
            env_file=str(env),
        )
        if rc != 0:
            print(f"  FAIL: rc={rc} stderr={err}")
            return False
        text = env.read_text(encoding="utf-8")
        if "MCP_SERVERS" in text:
            print(f"  FAIL: dry-run wrote to file:\n{text}")
            return False
        if "DRY RUN" not in out:
            print(f"  FAIL: should say DRY RUN, got: {out}")
            return False
        print(f"  OK: dry-run printed but didn't write")
        return True
    finally:
        env.unlink(missing_ok=True)


def test_end_to_end_manager_sees_new_entry() -> bool:
    """CLI adds → MCPManager reads .env → server comes up."""
    print("\n[cli-test 12] end-to-end: CLI add → manager.start() picks it up")
    env = fresh_env()
    # Save a backup of any real .env, and use our temp one instead.
    real_env = ROOT / ".env"
    backup_path = ROOT / ".env.cli_test_backup"
    if real_env.is_file():
        real_env.replace(backup_path)
    try:
        # Point the CLI at our temp .env, and also make MCPManager read it.
        # The manager uses os.environ.get("MCP_SERVERS") first, so we set
        # MCP_SERVERS directly to what the CLI would write.
        rc, _, err = run_cli(
            "add", "alpha",
            "--command", sys.executable,
            "--arg", str(ROOT / "tests" / "mcp_mock_server.py"),
            "--risk", "LOW",
            env_file=str(env),
        )
        if rc != 0:
            print(f"  FAIL: cli add failed: {err}")
            return False

        # Now mirror what .env contains into process env for the manager
        parsed = mcpcli.parse_env_var(env, "MCP_SERVERS")
        os.environ["MCP_SERVERS"] = parsed[2]

        import asyncio
        from src.mcp.manager import MCPManager
        from src.tools.registry import ToolRegistry

        async def go():
            registry = ToolRegistry()
            mgr = MCPManager(registry, config_path=Path("/nonexistent.yaml"))
            await mgr.start()
            try:
                return manager.servers  # noqa
            except Exception:
                pass
            return mgr.servers

        async def go2():
            registry = ToolRegistry()
            mgr = MCPManager(registry, config_path=Path("/nonexistent.yaml"))
            await mgr.start()
            servers = list(mgr.servers)
            await mgr.stop()
            return servers

        servers = asyncio.run(go2())
        if "alpha" not in servers:
            print(f"  FAIL: manager did not see 'alpha': {servers}")
            return False
        print(f"  OK: CLI write → MCPManager.start() picked up 'alpha'")
        return True
    finally:
        os.environ.pop("MCP_SERVERS", None)
        if backup_path.is_file():
            backup_path.replace(real_env)
        env.unlink(missing_ok=True)


def main() -> int:
    tests = [
        test_add_to_empty_env,
        test_add_with_args,
        test_add_replaces_existing,
        test_add_appends_to_existing,
        test_remove,
        test_remove_last_drops_line,
        test_remove_nonexistent,
        test_list_shows_servers,
        test_multiline_preservation,
        test_snippet_prints_only,
        test_dry_run_does_not_write,
        test_end_to_end_manager_sees_new_entry,
    ]
    results = []
    for t in tests:
        try:
            ok = t()
        except Exception as e:
            import traceback
            traceback.print_exc()
            ok = False
        results.append((t.__name__, ok))

    print("\n=== summary ===")
    for name, ok in results:
        print(f"  {'OK' if ok else 'FAIL'}  {name}")
    return 1 if any(not ok for _, ok in results) else 0


if __name__ == "__main__":
    sys.exit(main())
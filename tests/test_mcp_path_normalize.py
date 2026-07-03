r"""Tests for the dotenv-escape fix: windows path normalization in MCP CLI add.

python-dotenv 1.1.1 applies shell-style unescaping to single-quoted values,
which corrupts JSON containing Windows paths (e.g. `C:\Users\...` becomes
`C:\Users\...` and the JSON breaks). The CLI now auto-converts backslashes
to forward slashes in `command` and `args` values on Windows.

Run:  python tests/test_mcp_path_normalize.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.mcp import cli as mcpcli


def test_normalize_converts_command() -> bool:
    print("\n[norm-test 1] convert backslashes in command")
    server = {
        "name": "cua",
        "command": "C:\\Users\\TANG\\AppData\\Local\\Programs\\Cua\\cua-driver\\bin\\cua-driver.exe",
        "args": ["mcp"],
        "risk_level": "HIGH",
        "enabled": True,
    }
    out = mcpcli._normalize_windows_paths(server)
    if "\\" in out["command"]:
        print(f"  FAIL: still has backslashes: {out['command']}")
        return False
    if out["command"] != "C:/Users/TANG/AppData/Local/Programs/Cua/cua-driver/bin/cua-driver.exe":
        print(f"  FAIL: wrong normalization: {out['command']}")
        return False
    # Original should not be mutated (deepcopy)
    if "\\" not in server["command"]:
        print(f"  FAIL: original was mutated in place")
        return False
    print(f"  OK: {out['command']}")
    return True


def test_normalize_converts_args() -> bool:
    print("\n[norm-test 2] convert backslashes in args")
    server = {
        "name": "fs",
        "command": "npx",
        "args": ["-y", "@scope/server", "C:\\Users\\TANG\\Documents"],
        "risk_level": "MEDIUM",
        "enabled": True,
    }
    out = mcpcli._normalize_windows_paths(server)
    if "\\" in out["args"][-1]:
        print(f"  FAIL: last arg still has backslashes: {out['args']}")
        return False
    expected_path = "C:/Users/TANG/Documents"
    if out["args"][-1] != expected_path:
        print(f"  FAIL: last arg wrong: {out['args']}")
        return False
    # args without backslashes are left alone
    if out["args"][0] != "-y":
        print(f"  FAIL: -y was changed: {out['args']}")
        return False
    print(f"  OK: args normalized, flags preserved: {out['args']}")
    return True


def test_normalize_no_backslashes() -> bool:
    print("\n[norm-test 3] no backslashes = no-op")
    server = {
        "name": "everything",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-everything"],
        "risk_level": "LOW",
        "enabled": True,
    }
    out = mcpcli._normalize_windows_paths(server)
    if out != server:
        print(f"  FAIL: no-op case still modified dict: {out}")
        return False
    # Should also be the same object (deepcopy may still differ for nested)
    if out["args"] is not server["args"]:
        # Acceptable — deepcopy is fine
        pass
    print(f"  OK: untouched")
    return True


def test_upsert_normalizes() -> bool:
    print("\n[norm-test 4] _upsert applies normalization")
    servers = []
    new = {
        "name": "cua",
        "command": "C:\\path\\to\\cua-driver.exe",
        "args": ["mcp"],
        "risk_level": "HIGH",
        "enabled": True,
    }
    result = mcpcli._upsert(servers, new)
    if "\\" in result[0]["command"]:
        print(f"  FAIL: _upsert didn't normalize: {result[0]}")
        return False
    print(f"  OK: {result[0]['command']}")
    return True


def test_roundtrip_with_dotenv_like_parser() -> bool:
    """Simulate the dotenv 1.1.1 unescape behavior and verify JSON survives.

    python-dotenv applies C-style unescaping to single-quoted values:
        \\  →  \
        \n  →  newline
        \t  →  tab
    We verify that after this unescape, our stored JSON still parses and
    the paths are intact (because we already used forward slashes).
    """
    print("\n[norm-test 5] round-trip through dotenv-like unescape")

    # 1. User input with backslashes (Windows path)
    raw_input = {
        "name": "cua",
        "command": "C:\\Users\\TANG\\cua-driver.exe",
        "args": ["mcp"],
        "risk_level": "HIGH",
        "enabled": True,
    }
    # 2. CLI normalizes
    normalized = mcpcli._normalize_windows_paths(raw_input)
    # 3. CLI serializes to JSON
    serialized = json.dumps([normalized], ensure_ascii=False)
    # 4. The .env file would look like:  MCP_SERVERS='[...]'
    #    The value part after `=` (and any quote stripping + dotenv unescape)
    #    is what reaches _read_servers. Simulate that exactly:
    value_after_equals = f"'{serialized}'"
    # 5. dotenv 1.1.1 does C-style unescape on single-quoted values
    unescaped = value_after_equals.replace("\\\\", "\\")
    # 6. _strip_surrounding_quotes removes the outer '...'
    if unescaped.startswith("'") and unescaped.endswith("'"):
        unescaped = unescaped[1:-1]
    # 7. Parse
    try:
        data = json.loads(unescaped)
    except json.JSONDecodeError as e:
        print(f"  FAIL: JSON broke after dotenv unescape: {e}")
        print(f"    unescaped: {unescaped[:200]!r}")
        return False
    cmd = data[0]["command"]
    if cmd != "C:/Users/TANG/cua-driver.exe":
        print(f"  FAIL: path got mangled: {cmd!r}")
        return False
    print(f"  OK: survived round-trip, command = {cmd}")
    return True


def main() -> int:
    tests = [
        test_normalize_converts_command,
        test_normalize_converts_args,
        test_normalize_no_backslashes,
        test_upsert_normalizes,
        test_roundtrip_with_dotenv_like_parser,
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
    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main())
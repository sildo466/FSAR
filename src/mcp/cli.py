"""CLI for managing MCP server registrations in .env.

Designed for the "I just installed an MCP server via curl|sh, register it now"
flow. Reads MCP_SERVERS from .env (or process env), inserts or replaces the
named entry, writes back. Preserves comments and other variables.

Usage:
    python -m src.mcp.cli add <name> --command <cmd> [--arg X ...] [--risk LEVEL]
    python -m src.mcp.cli remove <name>
    python -m src.mcp.cli list
    python -m src.mcp.cli snippet <name> --command <cmd>   # print, don't write

Run from the FSAR project root so .env is auto-discovered. Pass --env-file
to override.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Ensure stdout uses UTF-8 so paths / logs with non-ASCII chars don't crash
# on Windows consoles that default to GBK.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# ---- .env parsing ----

def find_env_file(start: Path | None = None) -> Path:
    """Walk up from `start` (default cwd) looking for .env. Fallback to cwd/.env."""
    p = start or Path.cwd()
    for _ in range(6):
        candidate = p / ".env"
        if candidate.is_file():
            return candidate
        if p.parent == p:
            break
        p = p.parent
    return Path.cwd() / ".env"


def parse_env_var(path: Path, var: str) -> tuple[int, int, str] | None:
    """Find `VAR=...` in .env, return (start_line_idx, end_line_idx, raw_value).

    Handles multi-line values (e.g. JSON arrays that span lines). The value
    is returned exactly as it appears in the file — no quote stripping, no
    JSON parsing. That's the caller's job.

    Lines are tracked verbatim so the caller can splice the file back
    together without losing anything else.
    """
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    for i, line in enumerate(lines):
        if not _is_var_line(line, var):
            continue
        start = i
        # Extract everything after the first '='
        value_chunk = line.split("=", 1)[1].rstrip("\n").rstrip("\r")
        if _is_complete_value(value_chunk):
            return start, start, value_chunk

        # Multi-line — read until bracket / quote balance closes.
        j = i + 1
        collected = value_chunk
        while j < len(lines):
            collected += "\n" + lines[j].rstrip("\n").rstrip("\r")
            if _is_complete_value(collected):
                return start, j, collected
            j += 1
        # Unterminated — return what we have
        return start, j - 1, collected

    return None


def _is_var_line(line: str, var: str) -> bool:
    """True if line is a top-level `VAR=` assignment (not a comment, not a continuation)."""
    stripped = line.lstrip()
    if stripped.startswith("#"):
        return False
    if not stripped.startswith(f"{var}="):
        return False
    return True


def _is_complete_value(s: str) -> bool:
    """Heuristic: is this env value fully closed?

    - Wrapped in matching '...' or "..." → complete
    - Starts with `[` → must also end with `]` (otherwise still receiving lines)
    - Otherwise: complete if no newline (single-line value)
    """
    s = s.rstrip()
    if not s:
        return False
    if s[0] in ("'", '"') and s[-1] == s[0] and len(s) >= 2:
        return True
    if s.startswith("["):
        return s.endswith("]")
    return "\n" not in s


def write_env_block(path: Path, var: str, value: str) -> None:
    """Insert or replace `VAR=value` in .env, preserving all other content.

    The value is wrapped in single quotes so JSON inside is preserved
    verbatim and any `#`, `$`, or whitespace stays literal. Internal single
    quotes in the value are escaped using the POSIX-safe `'"'"'` trick.

    Read it back with parse_env_var() and strip the surrounding quotes (see
    _strip_surrounding_quotes) before json.loads.
    """
    escaped = value.replace("'", "'\"'\"'")
    new_block_lines = [f"{var}='{escaped}'\n"]

    if not path.is_file():
        path.write_text("".join(new_block_lines), encoding="utf-8")
        return

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    parsed = parse_env_var(path, var)

    if parsed is not None:
        start, end, _ = parsed
        lines = lines[:start] + new_block_lines + lines[end + 1:]
    else:
        # Append at end, with a comment marker for traceability
        if lines and not lines[-1].endswith("\n"):
            lines.append("\n")
        if lines and lines[-1].strip():
            lines.append("\n")
        lines.append("# Managed by FSAR MCP CLI\n")
        lines.extend(new_block_lines)

    path.write_text("".join(lines), encoding="utf-8")


def remove_env_block(path: Path, var: str) -> bool:
    """Remove `VAR=...` block entirely. Returns True if it existed."""
    parsed = parse_env_var(path, var)
    if parsed is None:
        return False
    start, end, _ = parsed
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    # Also drop the immediately preceding "Managed by FSAR MCP CLI" comment if present
    if start > 0 and "Managed by FSAR MCP CLI" in lines[start - 1]:
        start -= 1
    lines = lines[:start] + lines[end + 1:]
    path.write_text("".join(lines), encoding="utf-8")
    return True


# ---- Config load/save ----

def _read_servers(env_file: Path | None) -> list[dict]:
    """Read MCP_SERVERS from process env (preferred) or .env file.

    Strips surrounding single/double quotes if present, so values written
    by either dotenv style or shell heredoc style both parse.
    """
    raw = os.environ.get("MCP_SERVERS", "").strip()
    if not raw and env_file and env_file.is_file():
        parsed = parse_env_var(env_file, "MCP_SERVERS")
        if parsed:
            raw = parsed[2].strip()
    if not raw:
        return []
    raw = _strip_surrounding_quotes(raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"[fsar-mcp] WARN: MCP_SERVERS is invalid JSON: {e}", file=sys.stderr)
        return []
    if not isinstance(data, list):
        return []
    return [s for s in data if isinstance(s, dict)]


def _strip_surrounding_quotes(s: str) -> str:
    """Remove a single layer of matching '...' or \"...\" wrapping."""
    if len(s) >= 2:
        if s[0] == s[-1] and s[0] in ("'", '"'):
            return s[1:-1]
    return s


def _normalize_windows_paths(server: dict) -> dict:
    r"""Convert backslashes to forward slashes in `command` and `args`.

    Why: python-dotenv 1.1.1 applies shell-style unescaping to single-quoted
    values, so a backslash pair in a JSON string gets collapsed to a single
    backslash, corrupting the embedded Windows paths. Forward slashes work
    everywhere on Windows subprocesses, so we normalize before serialization.

    Only modifies Windows paths. Other strings (e.g. a literal backslash in
    a tool argument that isn't a path) are left alone — but in practice MCP
    server `command` and `args` are paths/flags, so this is safe.

    No-op on non-Windows platforms.
    """
    import copy
    if sys.platform != "win32":
        return server
    out = copy.deepcopy(server)
    cmd = out.get("command", "")
    if isinstance(cmd, str) and "\\" in cmd:
        out["command"] = cmd.replace("\\", "/")
    args = out.get("args", [])
    if isinstance(args, list):
        new_args = []
        for a in args:
            if isinstance(a, str) and "\\" in a:
                new_args.append(a.replace("\\", "/"))
            else:
                new_args.append(a)
        out["args"] = new_args
    return out


# ---- fsar.yaml helpers ----
#
# After fsar.yaml became the single source of truth for MCP server configs,
# the CLI needs to be able to read/write its `mcp.servers` block. The .env
# path remains as a fallback for users who haven't migrated yet — see the
# precedence rules in src/mcp/manager.py::_load_configs.


def find_fsar_yaml(start: Path | None = None) -> Path:
    """Walk up from `start` looking for config/fsar.yaml. Default to cwd/config/fsar.yaml."""
    p = start or Path.cwd()
    for _ in range(6):
        candidate = p / "config" / "fsar.yaml"
        if candidate.is_file():
            return candidate
        if p.parent == p:
            break
        p = p.parent
    return Path.cwd() / "config" / "fsar.yaml"


def read_fsar_mcp_servers(path: Path) -> list[dict]:
    """Read the `mcp.servers` list from fsar.yaml. Returns [] when absent."""
    import yaml

    if not path.is_file():
        return []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as e:
        print(f"[fsar-mcp] WARN: failed to read {path}: {e}", file=sys.stderr)
        return []
    return list(data.get("mcp", {}).get("servers", []) or [])


def write_fsar_mcp_servers(path: Path, servers: list[dict]) -> None:
    """Replace `mcp.servers` in fsar.yaml, preserving every other top-level section.

    Mirrors FsarConfig.save()'s atomic-write pattern (tmp + os.replace) so a
    mid-write crash doesn't leave a half-written YAML on disk.
    """
    import yaml

    if path.is_file():
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            data = {}
    else:
        data = {}
    data.setdefault("mcp", {})["servers"] = servers
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


# ---- Subcommands ----

def cmd_add(args) -> int:
    if args.fsar and args.env_file:
        print("[fsar-mcp] --fsar and --env-file are mutually exclusive", file=sys.stderr)
        return 1

    server: dict = {"name": args.name, "command": args.command}
    arg_list = _collect_args(args)
    if arg_list is not None:
        server["args"] = arg_list
    if args.risk:
        server["risk_level"] = args.risk.upper()
    if args.disabled:
        server["enabled"] = False
    else:
        # Default: enable on add (user is actively registering it)
        server["enabled"] = True

    if args.fsar:
        # Canonical path: write fsar.yaml's `mcp.servers` block.
        fsar_path = find_fsar_yaml()
        if args.dry_run:
            servers = read_fsar_mcp_servers(fsar_path)
            servers = _upsert(servers, server)
            print(f"[fsar-mcp] DRY RUN — would write to {fsar_path}:")
            print(f"mcp.servers = {json.dumps(servers, ensure_ascii=False, indent=2)}")
            return 0
        existed = any(s.get("name") == args.name for s in read_fsar_mcp_servers(fsar_path))
        servers = read_fsar_mcp_servers(fsar_path)
        servers = _upsert(servers, server)
        write_fsar_mcp_servers(fsar_path, servers)
        action = "updated" if existed else "added"
        print(f"[fsar-mcp] {action} '{args.name}' in {fsar_path}")
        print(f"[fsar-mcp] restart FSAR or run '/mcp reload' to activate.")
        return 0

    env_path = Path(args.env_file) if args.env_file else find_env_file()

    if args.dry_run:
        servers = _read_servers(env_path if env_path.exists() else None)
        servers = _upsert(servers, server)
        new_value = json.dumps(servers, ensure_ascii=False)
        print(f"[fsar-mcp] DRY RUN — would write to {env_path}:")
        print(f"MCP_SERVERS={json.dumps(new_value)}")
        return 0

    if not env_path.is_file() and not args.env_file:
        print(f"[fsar-mcp] no .env at {env_path}; creating one")

    servers = _read_servers(env_path if env_path.is_file() else None)
    servers = _upsert(servers, server)
    new_value = json.dumps(servers, ensure_ascii=False)

    write_env_block(env_path, "MCP_SERVERS", new_value)
    action = "updated" if any(s.get("name") == args.name and s != server for s in servers[:-1]) else "added"
    print(f"[fsar-mcp] {action} '{args.name}' in {env_path}")
    print(f"[fsar-mcp] restart FSAR or run '/mcp reload' to activate.")
    return 0


def _collect_args(args) -> list[str] | None:
    """Merge --arg (repeatable) and --args (JSON array) into one list."""
    parts: list[str] = []
    if getattr(args, "arg", None):
        parts.extend(args.arg)
    extra = getattr(args, "args_json", None)
    if extra:
        try:
            parsed = json.loads(extra)
        except json.JSONDecodeError as e:
            print(f"[fsar-mcp] WARN: --args is not valid JSON: {e}", file=sys.stderr)
            return parts or None
        if not isinstance(parsed, list):
            print(f"[fsar-mcp] WARN: --args must be a JSON array", file=sys.stderr)
            return parts or None
        parts.extend(str(x) for x in parsed)
    return parts or None


def cmd_remove(args) -> int:
    if args.fsar and args.env_file:
        print("[fsar-mcp] --fsar and --env-file are mutually exclusive", file=sys.stderr)
        return 1

    if args.fsar:
        fsar_path = find_fsar_yaml()
        servers = read_fsar_mcp_servers(fsar_path)
        filtered = [s for s in servers if s.get("name") != args.name]
        if len(filtered) == len(servers):
            print(f"[fsar-mcp] '{args.name}' not in {fsar_path}")
            return 1
        write_fsar_mcp_servers(fsar_path, filtered)
        print(f"[fsar-mcp] removed '{args.name}' from {fsar_path}")
        print(f"[fsar-mcp] restart FSAR or run '/mcp reload' to deactivate.")
        return 0

    env_path = Path(args.env_file) if args.env_file else find_env_file()
    if not env_path.is_file():
        print(f"[fsar-mcp] {env_path} not found", file=sys.stderr)
        return 1

    servers = _read_servers(env_path)
    filtered = [s for s in servers if s.get("name") != args.name]
    if len(filtered) == len(servers):
        print(f"[fsar-mcp] '{args.name}' not in MCP_SERVERS")
        return 1

    if filtered:
        new_value = json.dumps(filtered, ensure_ascii=False)
        write_env_block(env_path, "MCP_SERVERS", new_value)
    else:
        # No servers left — drop the line entirely
        remove_env_block(env_path, "MCP_SERVERS")

    print(f"[fsar-mcp] removed '{args.name}' from {env_path}")
    print(f"[fsar-mcp] restart FSAR or run '/mcp reload' to deactivate.")
    return 0


def cmd_list(args) -> int:
    if args.fsar and args.env_file:
        print("[fsar-mcp] --fsar and --env-file are mutually exclusive", file=sys.stderr)
        return 1

    if args.fsar:
        fsar_path = find_fsar_yaml()
        servers = read_fsar_mcp_servers(fsar_path)
        if not servers:
            print("(no MCP servers configured)")
            print(f"  config source: {fsar_path}")
            return 0
        print(f"source: {fsar_path}")
        for s in servers:
            name = s.get("name", "?")
            cmd = s.get("command", "?")
            cmd_args = " ".join(s.get("args") or [])
            risk = s.get("risk_level", "HIGH")
            enabled = "ON " if s.get("enabled", False) else "off"
            line = f"  [{enabled}] {name} ({risk}): {cmd} {cmd_args}".rstrip()
            print(line)
        return 0

    env_path = Path(args.env_file) if args.env_file else find_env_file()
    servers = _read_servers(env_path if env_path.is_file() else None)
    if not servers:
        print("(no MCP servers configured)")
        print(f"  config source: {env_path}")
        return 0
    print(f"source: {env_path}")
    for s in servers:
        name = s.get("name", "?")
        cmd = s.get("command", "?")
        cmd_args = " ".join(s.get("args") or [])
        risk = s.get("risk_level", "HIGH")
        enabled = "ON " if s.get("enabled", False) else "off"
        line = f"  [{enabled}] {name} ({risk}): {cmd} {cmd_args}".rstrip()
        print(line)
    return 0


def cmd_snippet(args) -> int:
    """Print a copy-pasteable snippet (does NOT touch .env)."""
    server: dict = {"name": args.name, "command": args.command}
    arg_list = _collect_args(args)
    if arg_list is not None:
        server["args"] = arg_list
    if args.risk:
        server["risk_level"] = args.risk.upper()
    if args.disabled:
        server["enabled"] = False
    else:
        server["enabled"] = True
    print(json.dumps(server, ensure_ascii=False))
    return 0


def _upsert(servers: list[dict], new: dict) -> list[dict]:
    """Replace existing entry with same name, else append.

    Also normalizes Windows paths in `new` (see _normalize_windows_paths)
    so any caller — including main.py's interactive /mcp add and /mcp install
    flows — gets the dotenv-safe representation.
    """
    new = _normalize_windows_paths(new)
    name = new.get("name")
    out = []
    replaced = False
    for s in servers:
        if s.get("name") == name:
            out.append(new)
            replaced = True
        else:
            out.append(s)
    if not replaced:
        out.append(new)
    return out


# ---- Entry point ----

def main() -> int:
    parser = argparse.ArgumentParser(
        prog="fsar-mcp",
        description="Manage MCP server registrations in .env",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add", help="Add or update an MCP server entry")
    p_add.add_argument("name", help="Server short name (e.g., filesystem)")
    p_add.add_argument("--command", required=True, help="Executable to spawn")
    p_add.add_argument(
        "--arg", action="append", default=[],
        help="Command argument (repeatable). For values starting with -, use --arg=-foo or --args JSON.",
    )
    p_add.add_argument(
        "--args",
        help='JSON array of command args, e.g. --args \'["-y","pkg","path"]\'. '
             "Use this when args start with -.",
    )
    p_add.add_argument(
        "--risk",
        help="Risk level: SAFE / LOW / MEDIUM / HIGH / CRITICAL (default HIGH)",
    )
    p_add.add_argument(
        "--enabled", action="store_true", default=True,
        help="Enable on add (default)",
    )
    p_add.add_argument(
        "--disabled", action="store_true", help="Add but don't enable",
    )
    p_add.add_argument("--env-file", help="Path to .env (default: auto-detect)")
    p_add.add_argument(
        "--fsar", action="store_true",
        help="Write to config/fsar.yaml (`mcp.servers`) instead of .env — "
             "use this after migrating MCP config into fsar.yaml.",
    )
    p_add.add_argument("--dry-run", action="store_true", help="Show what would be written")
    # Alias --args JSON to args_json internally so we can merge cleanly
    p_add.set_defaults(func=cmd_add, args_json=None)

    # argparse can't have two --args with different shapes, so use a sentinel
    # name internally and rename in pre-processing.
    # NOTE: argparse subparsers dispatch via parse_known_args, NOT parse_args,
    # so we must patch both.
    _orig_pka = p_add.parse_known_args

    def _extract_args_json(argv: list[str]) -> tuple[list[str], str | None]:
        new_argv: list[str] = []
        captured: str | None = None
        i = 0
        while i < len(argv):
            tok = argv[i]
            if tok == "--args" and i + 1 < len(argv):
                captured = argv[i + 1]
                i += 2
                continue
            if tok.startswith("--args="):
                captured = tok[len("--args="):]
                i += 1
                continue
            new_argv.append(tok)
            i += 1
        return new_argv, captured

    def _patched_pka(args=None, namespace=None):
        argv = sys.argv[1:] if args is None else list(args)
        new_argv, captured = _extract_args_json(argv)
        ns, extras = _orig_pka(new_argv, namespace)
        if captured is not None:
            ns.args_json = captured
        return ns, extras

    p_add.parse_known_args = _patched_pka  # type: ignore[assignment]
    # parse_args delegates to parse_known_args internally, but cover both
    p_add.parse_args = lambda args=None, namespace=None: _patched_pka(args, namespace)[0]  # type: ignore[assignment]

    p_rm = sub.add_parser("remove", help="Remove an MCP server entry")
    p_rm.add_argument("name")
    p_rm.add_argument("--env-file")
    p_rm.add_argument(
        "--fsar", action="store_true",
        help="Remove from config/fsar.yaml instead of .env",
    )
    p_rm.set_defaults(func=cmd_remove)

    p_ls = sub.add_parser("list", help="List configured MCP servers")
    p_ls.add_argument("--env-file")
    p_ls.add_argument(
        "--fsar", action="store_true",
        help="List from config/fsar.yaml instead of .env",
    )
    p_ls.set_defaults(func=cmd_list)

    p_sn = sub.add_parser("snippet", help="Print a single-server JSON snippet")
    p_sn.add_argument("name")
    p_sn.add_argument("--command", required=True)
    p_sn.add_argument("--arg", action="append", default=[])
    p_sn.add_argument(
        "--args",
        help="JSON array of args, e.g. --args '[\"-y\",\"pkg\"]'",
    )
    p_sn.add_argument("--risk")
    p_sn.add_argument("--disabled", action="store_true")
    p_sn.set_defaults(func=cmd_snippet, args_json=None)

    _sn_pka = p_sn.parse_known_args

    def _sn_patched(args=None, namespace=None):
        argv = sys.argv[1:] if args is None else list(args)
        new_argv, captured = _extract_args_json(argv)
        ns, extras = _sn_pka(new_argv, namespace)
        if captured is not None:
            ns.args_json = captured
        return ns, extras

    p_sn.parse_known_args = _sn_patched  # type: ignore[assignment]
    p_sn.parse_args = lambda args=None, namespace=None: _sn_patched(args, namespace)[0]  # type: ignore[assignment]

    args = parser.parse_args()
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
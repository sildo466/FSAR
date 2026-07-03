"""Built-in MCP server presets.

A small catalog of well-known MCP servers. Each preset has a command template
with placeholders the user fills in interactively (or via CLI flags).

To add a new preset:
    - key: short identifier used as the FSAR tool name prefix
    - description: one-line summary shown in /mcp install catalog
    - command, args: shell command template
    - risk_level: SAFE / LOW / MEDIUM / HIGH / CRITICAL
    - placeholders: list of {token, prompt, default, env_var?} for interactive
    - env: optional dict of extra env vars (supports ${VAR} expansion)

The installer fills <TOKEN> placeholders in args with user-supplied values.
"""

from __future__ import annotations

from typing import Any


MCP_PRESETS: dict[str, dict[str, Any]] = {
    "filesystem": {
        "description": "Read/write files in a directory (npx -y)",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "<DIR_PATH>"],
        "risk_level": "MEDIUM",
        "placeholders": [
            {
                "token": "<DIR_PATH>",
                "flag": "path",
                "prompt": "Directory to expose",
                "default": "${USERPROFILE}",
            },
        ],
    },
    "github": {
        "description": "GitHub repos, issues, PRs (needs GITHUB_TOKEN)",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "risk_level": "HIGH",
        "env": {"GITHUB_TOKEN": "${GITHUB_TOKEN}"},
        "placeholders": [],
    },
    "everything": {
        "description": "Test server with various tools (echo, sum, image)",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-everything"],
        "risk_level": "LOW",
        "placeholders": [],
    },
    "git": {
        "description": "Read git history of a repo (needs uvx)",
        "command": "uvx",
        "args": ["mcp-server-git", "--repository", "<REPO_PATH>"],
        "risk_level": "LOW",
        "placeholders": [
            {
                "token": "<REPO_PATH>",
                "flag": "repo",
                "prompt": "Path to git repository",
                "default": "${USERPROFILE}",
            },
        ],
    },
    "sqlite": {
        "description": "Query a SQLite database file (needs uvx)",
        "command": "uvx",
        "args": ["mcp-server-sqlite", "--db-path", "<DB_PATH>"],
        "risk_level": "MEDIUM",
        "placeholders": [
            {
                "token": "<DB_PATH>",
                "flag": "db",
                "prompt": "Path to .db file",
                "default": "",
            },
        ],
    },
    "fetch": {
        "description": "Fetch web pages and convert to markdown (needs uvx)",
        "command": "uvx",
        "args": ["mcp-server-fetch"],
        "risk_level": "MEDIUM",
        "placeholders": [],
    },
}


def list_presets() -> list[tuple[str, dict[str, Any]]]:
    """Return [(key, preset), ...] in display order."""
    return list(MCP_PRESETS.items())


def get_preset(key: str) -> dict[str, Any] | None:
    return MCP_PRESETS.get(key)


def fill_placeholders(
    preset: dict[str, Any], values: dict[str, str]
) -> dict[str, Any]:
    """Substitute <TOKEN> placeholders in args with values.

    Unknown tokens are left as-is so the user can debug. Values can use
    ${ENV_VAR} which gets expanded at subprocess spawn time (not here).
    """
    import copy
    out = copy.deepcopy(preset)
    args = []
    for a in out.get("args", []):
        if isinstance(a, str):
            for tok, val in values.items():
                a = a.replace(tok, val)
        args.append(a)
    out["args"] = args
    return out
"""MCPManager — multi-server lifecycle: load config, start, register tools, shut down.

Configuration sources (highest priority first):
    1. Environment variable `MCP_SERVERS` — JSON array of server objects.
       Convenient for deployment / Docker / copy-paste.
    2. YAML file at `config/mcp_servers.yaml` (or `config_path`) — for users
       who prefer editing a structured file. Useful for ${VAR} interpolation.

Spawns one `MCPClient` per enabled server, queries `tools/list`, and wraps
each tool into an `MCPTool` registered into the supplied `ToolRegistry`.

Failure policy: one broken server must not break others or block FSAR startup.
Each server is started in its own try/except so we log and skip on error.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import yaml
from mcp import StdioServerParameters

from src.mcp.client import MCPClient
from src.mcp.tool import MCPTool
from src.tools.registry import Tool, ToolRegistry
from src.utils.logger import logger as log


VALID_RISK_LEVELS = {"SAFE", "LOW", "MEDIUM", "HIGH", "CRITICAL"}
DEFAULT_RISK = "HIGH"  # MCP tools can do anything → default to highest caution
ENV_VAR_NAME = "MCP_SERVERS"  # JSON-encoded list of server configs


def _strip_surrounding_quotes(s: str) -> str:
    """Remove one matching layer of '...' or \"...\" wrapping, if present."""
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        return s[1:-1]
    return s


class MCPManager:
    def __init__(
        self,
        registry: ToolRegistry,
        config_path: str | Path = "config/mcp_servers.yaml",
        env_var: str = ENV_VAR_NAME,
        fsar_servers: list[dict] | None = None,
    ):
        self._registry = registry
        self._config_path = Path(config_path)
        self._env_var = env_var
        # Pre-loaded server list from fsar.yaml (`mcp.servers`). When non-empty
        # this takes precedence over both the env var and the YAML file, so a
        # user migrating to a single fsar.yaml gets one source of truth without
        # having to delete the old YAML.
        self._fsar_servers: list[dict] = list(fsar_servers or [])
        self._clients: dict[str, MCPClient] = {}
        self._registered_tools: list[Tool] = []
        self._started: dict[str, bool] = {}
        # Tools the user has explicitly removed via API but server still
        # re-exposes; we suppress them on next start(). Keyed by MCPTool.name.
        self._disabled_tools: set[str] = set()

    # --- public API ---

    @property
    def servers(self) -> list[str]:
        return list(self._clients.keys())

    def get_client(self, server_name: str) -> MCPClient | None:
        return self._clients.get(server_name)

    async def start(self) -> None:
        """Start all enabled servers, register their tools.

        Servers that fail to start are logged and skipped — the rest still
        come up. Tools registered from a server that fails are simply absent.
        """
        configs = self._load_configs()
        if not configs:
            log.info("MCP: no servers configured (set MCP_SERVERS env var "
                     f"or create {self._config_path})")
            return

        # Start servers in parallel — each is its own subprocess with its own
        # failure mode. await gather(return_exceptions=True) so one bad
        # server doesn't poison the others.
        results = await asyncio.gather(
            *(self._start_one(cfg) for cfg in configs),
            return_exceptions=True,
        )
        for cfg, res in zip(configs, results):
            if isinstance(res, Exception):
                log.error(f"MCP server '{cfg['name']}' failed: {res}")

        n_servers = sum(1 for v in self._started.values() if v)
        n_tools = sum(
            1 for t in self._registered_tools if t.name not in self._disabled_tools
        )
        log.info(f"MCP: {n_servers}/{len(configs)} servers up, {n_tools} tools registered")

    async def stop(self) -> None:
        for client in list(self._clients.values()):
            try:
                await client.stop()
            except Exception as e:
                log.warning(f"MCP[{client.name}] stop error: {e}")
        self._clients.clear()
        # Tools remain in the registry; their execute() will fail until
        # the server is restarted. We intentionally don't deregister — the
        # caller may want to call reload().

    async def reload(self) -> None:
        """Stop everything, re-read config, start again."""
        # Strip previously-registered MCP tools from the registry first so we
        # don't accumulate duplicates on reload.
        for tool in self._registered_tools:
            self._registry._tools.pop(tool.name, None)  # type: ignore[attr-defined]
        self._registered_tools.clear()
        await self.stop()
        await self.start()

    def disable_tool(self, tool_name: str) -> bool:
        """Hide a single MCP tool from the LLM (it stays loadable by name)."""
        # We don't remove from registry (Tool ABC isn't built for that) — we
        # mark it so list_tools hides it. execute() still works if called.
        self._disabled_tools.add(tool_name)
        return True

    def list_visible_tools(self) -> list[Tool]:
        return [t for t in self._registered_tools if t.name not in self._disabled_tools]

    # --- internals ---

    def _load_configs(self) -> list[dict[str, Any]]:
        """Read server configurations.

        Precedence (highest first):
            1. fsar.yaml `mcp.servers` (when non-empty — set via __init__ arg)
            2. Environment variable MCP_SERVERS (JSON array)
            3. YAML file at `config/mcp_servers.yaml` (or `config_path`)

        fsar.yaml is the single source of truth once populated, so the env
        var / YAML path remains as a fallback for users who haven't migrated.
        """
        if self._fsar_servers:
            log.info(
                f"MCP: loaded {len(self._fsar_servers)} server(s) from fsar.yaml"
            )
            return self._validate(self._fsar_servers)

        env_raw = os.environ.get(self._env_var, "").strip()
        if env_raw:
            # Tolerate values that include surrounding quotes — both forms
            # occur in practice: shell-exported values are usually clean, but
            # values lifted directly from .env files (e.g. by tools that don't
            # run the file through a parser) carry the wrapping quotes.
            env_raw = _strip_surrounding_quotes(env_raw)
            try:
                raw_list = json.loads(env_raw)
            except json.JSONDecodeError as e:
                log.error(
                    f"MCP: invalid JSON in {self._env_var}: {e}. "
                    f"Falling back to {self._config_path}."
                )
                return self._load_yaml()
            if not isinstance(raw_list, list):
                log.error(
                    f"MCP: {self._env_var} must be a JSON array, "
                    f"got {type(raw_list).__name__}. "
                    f"Falling back to {self._config_path}."
                )
                return self._load_yaml()
            log.info(f"MCP: loaded {len(raw_list)} server(s) from {self._env_var}")
            return self._validate(raw_list)

        return self._load_yaml()

    def _load_yaml(self) -> list[dict[str, Any]]:
        """Read + validate the YAML config file. Returns [] on any failure."""
        if not self._config_path.exists():
            return []
        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except (OSError, yaml.YAMLError) as e:
            log.error(f"MCP: failed to read {self._config_path}: {e}")
            return []
        servers = data.get("servers", []) or []
        log.info(f"MCP: loaded {len(servers)} server(s) from {self._config_path}")
        return self._validate(servers)

    def _validate(self, servers: list[Any]) -> list[dict[str, Any]]:
        """Normalize and validate server entries. Drops disabled / malformed ones."""
        out: list[dict[str, Any]] = []
        for s in servers:
            if not isinstance(s, dict):
                log.warning(f"MCP: entry is not an object, skipping: {s!r}")
                continue
            name = s.get("name")
            if not name:
                log.warning(f"MCP server entry missing 'name', skipping: {s}")
                continue
            if not s.get("enabled", False):
                continue
            transport = (s.get("transport") or "stdio").lower()
            if transport != "stdio":
                log.warning(f"MCP server '{name}': transport '{transport}' not supported yet, skipping")
                continue
            command = s.get("command")
            if not command:
                log.warning(f"MCP server '{name}': missing 'command', skipping")
                continue
            risk = (s.get("risk_level") or DEFAULT_RISK).upper()
            if risk not in VALID_RISK_LEVELS:
                log.warning(f"MCP server '{name}': invalid risk_level '{risk}', using {DEFAULT_RISK}")
                risk = DEFAULT_RISK
            out.append({
                "name": name,
                "command": command,
                "args": s.get("args") or [],
                "env": s.get("env") or {},
                "cwd": s.get("cwd"),
                "risk_level": risk,
                "_raw": s,
            })
        return out

    async def _start_one(self, cfg: dict[str, Any]) -> None:
        name = cfg["name"]
        # Expand ${VAR} placeholders in env
        env = self._expand_env(cfg["env"])
        client = MCPClient(
            name=name,
            command=cfg["command"],
            args=cfg["args"],
            env=env,
            cwd=cfg["cwd"],
        )
        self._clients[name] = client
        try:
            await client.start()
            self._started[name] = True
        except Exception as e:
            self._started[name] = False
            log.error(f"MCP[{name}] start failed: {e}")
            # Best-effort cleanup so the subprocess isn't leaked
            try:
                await client.stop()
            except Exception:
                pass
            self._clients.pop(name, None)
            return

        try:
            tools = await client.list_tools()
        except Exception as e:
            log.error(f"MCP[{name}] list_tools failed: {e}")
            return

        for tdef in tools:
            mtool = MCPTool(
                server_name=name,
                tool_def=tdef,
                client=client,
                risk_level=cfg["risk_level"],
            )
            self._registry.register(mtool)
            self._registered_tools.append(mtool)
        log.info(
            f"MCP[{name}]: {len(tools)} tools registered "
            f"(risk={cfg['risk_level']})"
        )

    @staticmethod
    def _expand_env(env: dict[str, str]) -> dict[str, str]:
        """Expand ${VAR} and $VAR in env values using process env."""
        result: dict[str, str] = {}
        for k, v in env.items():
            if not isinstance(v, str):
                continue
            # os.path.expandvars handles both $VAR and ${VAR}
            result[k] = os.path.expandvars(v)
        return result
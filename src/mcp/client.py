"""MCP stdio client — owns one subprocess + one ClientSession.

Wraps `mcp.client.stdio.stdio_client` and `mcp.client.session.ClientSession`
so the rest of FSAR deals with one object: `.start()` → `.list_tools()` /
`.call_tool()` → `.stop()`.

Designed to run inside `MCPManager`; one client per server.
"""

from __future__ import annotations

import asyncio
import os
import sys
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from src.utils.logger import logger as log


class MCPClient:
    """Async wrapper around one MCP server subprocess (stdio transport)."""

    def __init__(
        self,
        name: str,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
    ):
        self.name = name
        self._command = command
        self._args = args or []
        # Inherit parent env unless caller overrides
        self._env = dict(os.environ) if env is None else {**os.environ, **env}
        self._cwd = cwd

        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self._server_info: dict[str, Any] = {}
        self._started = False
        self._lock = asyncio.Lock()

    @property
    def started(self) -> bool:
        return self._started and self._session is not None

    @property
    def server_info(self) -> dict[str, Any]:
        return dict(self._server_info)

    async def start(self) -> None:
        """Spawn subprocess, perform MCP initialize handshake.

        Raises on failure (caller decides whether to retry / skip the server).
        """
        if self._started:
            return
        async with self._lock:
            if self._started:
                return

            # On Windows, stdio MCP servers often fail when launched as a
            # detached console process because Python's default stdio
            # handling loses buffered bytes. Setting PYTHONUNBUFFERED on the
            # child and using a CREATE_NO_WINDOW process flag (set inside
            # stdio_client) keeps streams reliable. Nothing to do here — the
            # SDK handles it — but we ensure PATH is inherited.
            if sys.platform == "win32" and "PATH" not in self._env:
                self._env["PATH"] = os.environ.get("PATH", "")

            params = StdioServerParameters(
                command=self._command,
                args=self._args,
                env=self._env,
                cwd=self._cwd,
            )

            self._stack = AsyncExitStack()
            try:
                read, write = await self._stack.enter_async_context(stdio_client(params))
                self._session = await self._stack.enter_async_context(
                    ClientSession(read, write)
                )
                init_result = await self._session.initialize()
                # init_result is an InitializeResult; surface useful fields
                info = getattr(init_result, "serverInfo", None) or getattr(init_result, "server_info", None)
                if info is not None:
                    self._server_info = {
                        "name": getattr(info, "name", "?"),
                        "version": getattr(info, "version", "?"),
                    }
                log.info(
                    f"MCP[{self.name}] connected: "
                    f"{self._server_info.get('name', '?')} "
                    f"v{self._server_info.get('version', '?')}"
                )
                self._started = True
            except Exception:
                # Cleanup on partial start
                await self._safe_close_stack()
                raise

    async def list_tools(self) -> list[Any]:
        if not self.started:
            raise RuntimeError(f"MCP[{self.name}] not started")
        result = await self._session.list_tools()
        return list(result.tools)

    async def call_tool(self, name: str, arguments: dict) -> Any:
        if not self.started:
            raise RuntimeError(f"MCP[{self.name}] not started")
        return await self._session.call_tool(name=name, arguments=arguments)

    async def stop(self) -> None:
        async with self._lock:
            await self._safe_close_stack()
            self._started = False
            self._session = None

    async def _safe_close_stack(self) -> None:
        if self._stack is None:
            return
        try:
            await self._stack.aclose()
        except Exception as e:
            # The MCP SDK ties stdio_client's cancel scope to the task that
            # called start(). If stop() runs in a different task (e.g. when
            # MCPManager.reload() runs in a new asyncio.gather task), the
            # scope can't be exited cleanly and AnyIO raises. This is
            # cosmetic — the subprocess is killed regardless. Log at debug.
            log.debug(f"MCP[{self.name}] close error (cross-task): {e}")
        finally:
            self._stack = None
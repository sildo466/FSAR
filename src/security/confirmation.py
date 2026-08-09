"""FSAR confirmation mechanism — CLI-style confirmation prompt.

Async, does not block the event loop; default-deny on timeout.
Supports up to five replies depending on whether a server_name is present:
  y          → approve once
  n          → deny this one
  all        → approve for the rest of this session (caller invokes PermissionState.set_session_trust)
  server     → trust the whole MCP server for this session (only shown when server_name is set)
  never      → permanently deny (caller invokes PermissionState.set_permanent_deny)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional


class ConfirmResponse(Enum):
    YES = "y"
    NO = "n"
    ALL = "all"   # session-scoped trust for this specific tool
    SERVER_TRUST = "server"  # session-scoped trust for the whole MCP server
    NEVER = "never"  # permanent deny


@dataclass
class ConfirmResult:
    response: ConfirmResponse
    raw: str


async def ask_user(tool_name: str, args: dict, reason: str,
                   on_trust: Optional[Callable[[str], None]] = None,
                   on_deny: Optional[Callable[[str], None]] = None,
                   on_server_trust: Optional[Callable[[str], None]] = None,
                   server_name: Optional[str] = None,
                   timeout: float = 120.0) -> ConfirmResult:
    """Block on input() for the user's reply. Returns ConfirmResult.

    on_trust:        callback used to update session_trust for `tool_name`.
    on_deny:         callback used to set a permanent deny for `tool_name`.
    on_server_trust: callback used to update server_trust for `server_name`.
                     Only effective when `server_name` is provided.
    server_name:     if set, an extra [server] option is shown in the prompt.
    """

    print()
    print(f"[!] FSAR wants to execute: {tool_name}")
    # Truncate args preview to avoid screen spam
    args_preview = _preview_args(args)
    print(f"    Args: {args_preview}")
    print(f"    Reason: {reason}")
    server_opt = f"   [server] trust MCP server '{server_name}' for this session" if server_name else ""
    print(
        f"    [y] approve once   [n] deny   [all] trust this tool for this session"
        f"{server_opt}   [never] permanently deny"
    )
    print(f"    Choice (default n, timeout {timeout:.0f}s):")

    loop = asyncio.get_event_loop()

    try:
        raw = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: input("    > ").strip().lower()),
            timeout=timeout,
        )
    except (asyncio.TimeoutError, EOFError):
        raw = "n"

    if raw in ("all", "a"):
        if on_trust:
            on_trust(tool_name)
        return ConfirmResult(ConfirmResponse.ALL, raw)
    if raw in ("server", "s") and server_name:
        if on_server_trust:
            on_server_trust(server_name)
        return ConfirmResult(ConfirmResponse.SERVER_TRUST, raw)
    if raw in ("never", "v"):
        if on_deny:
            on_deny(tool_name)
        return ConfirmResult(ConfirmResponse.NEVER, raw)
    if raw in ("y", "yes"):
        return ConfirmResult(ConfirmResponse.YES, raw)
    # Default n (including plain Enter)
    return ConfirmResult(ConfirmResponse.NO, raw or "n")


def _preview_args(args: dict) -> str:
    s = ", ".join(f"{k}={_short(v)}" for k, v in args.items())
    if len(s) > 200:
        s = s[:197] + "..."
    return s or "(none)"


def _short(v) -> str:
    if isinstance(v, str):
        return repr(v[:80])
    return repr(v)

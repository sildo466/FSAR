# SPDX-License-Identifier: MIT
"""Async bridge for risk confirm — backend asks via WS, frontend replies."""

from __future__ import annotations

import asyncio
from typing import Any

from src.security.confirmation import ConfirmResponse


class RiskBridge:
    def __init__(self) -> None:
        self._pending: dict[str, asyncio.Future[ConfirmResponse]] = {}
        self._pending_info: dict[str, tuple[str, str, str]] = {}

    async def submit(
        self, call_id: str, tool: str, args_preview: str, reason: str,
        *, timeout: float = 30.0,
    ) -> ConfirmResponse:
        """Caller awaits this future; UI must call respond() with the user's choice."""
        fut: asyncio.Future[ConfirmResponse] = asyncio.get_running_loop().create_future()
        self._pending[call_id] = fut
        self._pending_info[call_id] = (tool, args_preview, reason)
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            return ConfirmResponse.NO
        finally:
            self._pending.pop(call_id, None)
            self._pending_info.pop(call_id, None)

    def respond(self, call_id: str, response: ConfirmResponse) -> bool:
        fut = self._pending.get(call_id)
        if fut is None or fut.done():
            return False
        fut.set_result(response)
        return True

    def pending(self) -> dict[str, dict[str, Any]]:
        return {
            cid: {"tool": tool, "args_preview": args, "reason": r}
            for cid, (tool, args, r) in self._pending_info.items()
        }

"""Async bridge for sandbox escape decisions."""

from __future__ import annotations

import asyncio


VALID_DECISIONS = {"deny", "allow_once", "allow_session", "allow_always"}


class SandboxBridge:
    def __init__(self) -> None:
        self._pending: dict[str, asyncio.Future[str]] = {}

    async def submit(self, request_id: str, *, timeout: float = 60.0) -> str:
        future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            return "deny"
        finally:
            self._pending.pop(request_id, None)

    def respond(self, request_id: str, decision: str) -> bool:
        future = self._pending.get(request_id)
        if decision not in VALID_DECISIONS or future is None or future.done():
            return False
        future.set_result(decision)
        return True

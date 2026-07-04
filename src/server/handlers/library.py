# SPDX-License-Identifier: Apache-2.0
"""WS dispatcher for library CRUD + archive (implemented in Task 30)."""

from __future__ import annotations

from typing import Any

from fastapi import WebSocket


async def dispatch(ws: WebSocket, msg: dict[str, Any], ctx: dict[str, Any] | None = None) -> bool:
    return False
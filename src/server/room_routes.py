# SPDX-License-Identifier: MIT
"""The LAN routes.

Kept apart from room_app.py so the app's surface — what exists at all — can be
read in one place, and so every handler has to pass through the same
auth_guard. The four routes arrive in T9 (index), T10 (state), T11 (messages)
and T12 (agent.md).
"""

from __future__ import annotations

from typing import Any


def register_routes(app: Any, deps: Any) -> None:
    return None

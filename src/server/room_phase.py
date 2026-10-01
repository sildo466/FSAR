# SPDX-License-Identifier: MIT
"""Where a room goes next, decided from the board alone.

Kept pure so the whole machine is exhaustible in a test; the runner owns the
IO and only asks this what the answer is.
"""

from __future__ import annotations

from typing import Any

PHASES = ("chat", "planning", "working", "review", "done")
DISPATCHABLE_STATUSES = frozenset({"todo"})


def is_dispatchable(item: Any) -> bool:
    return (
        str(getattr(item, "status", "")) in DISPATCHABLE_STATUSES
        and getattr(item, "owner_ref", None) is not None
    )


def decide_phase(
    phase: str, items: list[Any], *, in_flight: int,
) -> tuple[str, str] | None:
    """(next_phase, reason), or None when the phase does not change."""
    if phase == "planning":
        if items and all(getattr(i, "owner_ref", None) for i in items):
            return "working", "all_owned"
        return None
    if phase != "working":
        return None
    if in_flight > 0:
        return None
    if any(is_dispatchable(i) for i in items):
        return None
    if not items:
        return "review", "all_done"
    if all(str(i.status) == "done" for i in items):
        return "review", "all_done"
    if any(str(i.status) == "blocked" for i in items):
        return "review", "all_blocked"
    if any(str(i.status) == "todo" for i in items):
        return "review", "no_owner"
    return "review", "all_done"

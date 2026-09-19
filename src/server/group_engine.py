# SPDX-License-Identifier: MIT
"""Group chat orchestration: election, chained turns, cancellation."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from src.memory.session_store import MessageRow

if TYPE_CHECKING:
    from src.memory.rooms import RoomStore
    from src.server.chat_engine import ChatEngine


UNKNOWN_SPEAKER = "Unknown"

_EAGERNESS_RE = re.compile(r'\{[^{}]*"eagerness"[^{}]*\}', re.DOTALL)


def parse_eagerness(raw: str) -> tuple[int, str]:
    """Extract (eagerness, reason) from an election reply.

    Locates the JSON object by regex so markdown fences and surrounding prose
    are tolerated. Any failure yields (0, "") — a character that cannot answer
    simply stays silent this round."""
    if not raw:
        return 0, ""
    match = _EAGERNESS_RE.search(raw)
    if match is None:
        return 0, ""
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return 0, ""
    try:
        score = int(data.get("eagerness", 0))
    except (TypeError, ValueError):
        return 0, ""
    reason = str(data.get("reason", "") or "").strip()[:200]
    return max(0, min(10, score)), reason


def format_group_history(
    messages: list[MessageRow],
    *,
    names_by_id: dict[int, str],
    user_name: str,
) -> list[dict[str, str]]:
    """Prefix every message with its speaker.

    Every character message shares role="assistant", so without a prefix the
    model cannot tell who said what."""
    out: list[dict[str, str]] = []
    for row in messages:
        if row.role == "user":
            speaker = user_name or "user"
        else:
            speaker = names_by_id.get(row.character_card_id or -1, UNKNOWN_SPEAKER)
        out.append({
            "role": row.role,
            "content": f"[{speaker}]: {row.content}",
        })
    return out

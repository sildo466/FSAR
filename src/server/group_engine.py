# SPDX-License-Identifier: MIT
"""Group chat orchestration: election, chained turns, cancellation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.memory.session_store import MessageRow

if TYPE_CHECKING:
    from src.memory.rooms import RoomStore
    from src.server.chat_engine import ChatEngine


UNKNOWN_SPEAKER = "Unknown"


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

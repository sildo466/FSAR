# SPDX-License-Identifier: Apache-2.0
"""WS dispatcher for library CRUD + archive."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import WebSocket

from src.memory.experience_store import ExperienceStore


def _default_db() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "fsar_memory.db"


def _resolve_db(ctx: dict[str, Any] | None) -> Path:
    if ctx and ctx.get("db_path"):
        return Path(ctx["db_path"])
    return _default_db()


async def dispatch(ws: WebSocket, msg: dict[str, Any], ctx: dict[str, Any] | None = None) -> bool:
    t = msg.get("type")
    if not t or not t.startswith("library."):
        return False
    store = ExperienceStore(_resolve_db(ctx))
    now = datetime.now().isoformat(timespec="seconds")

    if t == "library.list":
        exps = store.list_for_index(include_states=("active", "stale", "archived"))
        await ws.send_json({
            "type": "library.list_result",
            "experiences": [e.to_dict() for e in exps],
        })
        return True

    if t == "library.create":
        from src.memory.experience_store import Experience
        store.upsert_experience(Experience(
            name=msg["name"],
            category=msg["category"],
            description=msg.get("description", ""),
            body=msg["body"],
            created_by=msg.get("created_by", "user"),
            created_at=now,
        ))
        await ws.send_json({"type": "library.changed", "op": "create", "name": msg["name"]})
        return True

    if t == "library.update":
        from src.memory.experience_store import Experience
        existing = store.get_by_name(msg["name"])
        if existing is None:
            await ws.send_json({"type": "error", "code": "not_found", "message": msg["name"], "recoverable": True})
            return True
        merged = Experience(
            id=existing.id,
            name=msg["name"],
            category=msg.get("category", existing.category),
            description=msg.get("description", existing.description),
            body=msg.get("body", existing.body),
            trigger_patterns=existing.trigger_patterns,
            pitfalls=existing.pitfalls,
            prerequisites=existing.prerequisites,
            use_count=existing.use_count,
            last_used_at=existing.last_used_at,
            state=existing.state,
            pinned=existing.pinned,
            created_by=existing.created_by,
            created_at=existing.created_at,
        )
        store.upsert_experience(merged)
        await ws.send_json({"type": "library.changed", "op": "update", "name": msg["name"]})
        return True

    if t == "library.archive":
        store.set_state(msg["name"], "archived")
        await ws.send_json({"type": "library.changed", "op": "archive", "name": msg["name"]})
        return True

    return False
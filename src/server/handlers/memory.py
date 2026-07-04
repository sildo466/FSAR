# SPDX-License-Identifier: Apache-2.0
"""WS dispatcher for memory search + remember."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import WebSocket


def _default_db() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "fsar_memory.db"


def _resolve_db(ctx: dict[str, Any] | None) -> Path:
    if ctx and ctx.get("db_path"):
        return Path(ctx["db_path"])
    return _default_db()


async def dispatch(ws: WebSocket, msg: dict[str, Any], ctx: dict[str, Any] | None = None) -> bool:
    t = msg.get("type")
    if t == "memory.search":
        from src.memory.recall import MemoryRecall

        query = msg.get("query", "")
        out: list[dict[str, Any]] = []
        try:
            recall = MemoryRecall(experience_store=_make_store(ctx))
            result = recall.recall_for_context(query)
            for c in result.similar_conversations[:5]:
                md = c.get("metadata", {}) if isinstance(c, dict) else {}
                dist = md.get("distance")
                out.append({
                    "session_id": md.get("session_id", ""),
                    "snippet": c.get("text", "")[:200] if isinstance(c, dict) else str(c)[:200],
                    "score": 1.0 - float(dist) if dist is not None else 1.0,
                })
        except Exception:
            out = []
        await ws.send_json({"type": "memory.search_results", "query": query, "results": out})
        return True
    if t == "memory.remember":
        from src.memory.experience_store import ExperienceStore

        store = ExperienceStore(_resolve_db(ctx))
        body = msg.get("body", "")
        store.add_chunk(source="memory", title=body[:60] or "(empty)", body=body)
        return True
    return False


def _make_store(ctx: dict[str, Any] | None):
    from src.memory.experience_store import ExperienceStore
    return ExperienceStore(_resolve_db(ctx))
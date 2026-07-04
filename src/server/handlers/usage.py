# SPDX-License-Identifier: Apache-2.0
"""WS dispatcher for Usage page: token rollups + cache breakdown."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import WebSocket


def _default_db() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "memory.db"


def _default_cache_db() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "llm_cache.db"


def _resolve_db(ctx: dict[str, Any] | None) -> Path:
    if ctx and ctx.get("db_path"):
        return Path(ctx["db_path"])
    return _default_db()


def _resolve_cache_db(ctx: dict[str, Any] | None) -> Path:
    if ctx and ctx.get("cache_db_path"):
        return Path(ctx["cache_db_path"])
    return _default_cache_db()


def _build_snapshot(db_path: Path, cache_db: Path, from_ts: str, to_ts: str) -> dict[str, Any]:
    from src.memory.decision_log import DecisionLog
    from src.utils.llm_cache import LLMCache

    log = DecisionLog(db_path=db_path)
    totals = log.get_token_totals()
    rows_total = log.get_total()
    cache = LLMCache(db_path=str(cache_db))
    cache_stats = cache.get_stats()

    total_tokens = totals["total_tokens"]
    cached_tokens = totals["cached_tokens"]
    cache_hit_pct = (
        round(100.0 * cached_tokens / total_tokens, 1) if total_tokens else 0.0
    )

    stats = log.get_stats(min_uses=1)
    per_tool = [
        {
            "tool": s["tool_name"],
            "calls": s["total_uses"],
            "tokens_in": 0,
            "tokens_out": 0,
            "success_rate_pct": s["success_rate_pct"],
            "avg_latency_ms": s["avg_latency_ms"],
        }
        for s in stats
    ]

    return {
        "kpis": {
            "total_tokens": total_tokens,
            "prompt_tokens": totals["prompt_tokens"],
            "completion_tokens": totals["completion_tokens"],
            "cached_tokens": cached_tokens,
            "cache_hit_pct": cache_hit_pct,
            "estimated_cost_usd": 0.0,
            "decision_rows": rows_total,
            "from": from_ts,
            "to": to_ts,
        },
        "timeline": [],
        "per_provider": [],
        "per_tool": per_tool,
        "cache": cache_stats,
    }


async def dispatch(ws: WebSocket, msg: dict[str, Any], ctx: dict[str, Any] | None = None) -> bool:
    if msg.get("type") == "usage.range":
        db = _resolve_db(ctx)
        cache_db = _resolve_cache_db(ctx)
        snap = _build_snapshot(
            db,
            cache_db,
            from_ts=str(msg.get("from", "")),
            to_ts=str(msg.get("to", "")),
        )
        await ws.send_json({"type": "usage.snapshot", **snap})
        return True
    return False

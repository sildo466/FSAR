# SPDX-License-Identifier: MIT
"""WS dispatcher for Usage page: token rollups + cache breakdown."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import WebSocket


def _default_db() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "memory.db"


def _default_cache_db() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "llm_cache.db"


def compute_cost(prompt_tokens: int, completion_tokens: int, pricing: dict | None) -> float:
    """Pure: (prompt/1e6) * input_per_1m + (completion/1e6) * output_per_1m.

    Pricing dict follows FsarConfig.llm.providers[].pricing shape.
    Rate unit is USD per 1,000,000 tokens (matches what vendors publish,
    e.g. OpenAI gpt-4o-mini = 0.15 / 0.60 per 1M). Returns 0.0 when pricing
    is missing or has no rate fields.
    """
    if not pricing:
        return 0.0
    in_per_1m = float(pricing.get("input_per_1m", 0) or 0)
    out_per_1m = float(pricing.get("output_per_1m", 0) or 0)
    return round(
        (prompt_tokens / 1_000_000.0) * in_per_1m
        + (completion_tokens / 1_000_000.0) * out_per_1m,
        10,
    )


def _resolve_db(ctx: dict[str, Any] | None) -> Path:
    if ctx and ctx.get("db_path"):
        return Path(ctx["db_path"])
    return _default_db()


def _resolve_cache_db(ctx: dict[str, Any] | None) -> Path:
    if ctx and ctx.get("cache_db_path"):
        return Path(ctx["cache_db_path"])
    return _default_cache_db()


def _build_snapshot(db_path: Path, cache_db: Path, from_ts: str, to_ts: str,
                    config: Any = None) -> dict[str, Any]:
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

    with log._connect() as conn:
        timeline = [
            {
                "date": r[0],
                "prompt_tokens": r[1] or 0,
                "completion_tokens": r[2] or 0,
                "cached_tokens": r[3] or 0,
            }
            for r in conn.execute(
                "SELECT date(created_at), SUM(prompt_tokens), SUM(completion_tokens),"
                " SUM(cached_tokens) FROM decision_log"
                " WHERE date(created_at) BETWEEN date(?) AND date(?)"
                " GROUP BY date(created_at) ORDER BY date(created_at)",
                (from_ts, to_ts),
            ).fetchall()
        ]

    pricing = None
    active = {}
    if config is not None:
        active = config.get_active_provider() or {}
        pricing = active.get("pricing")
    estimated_cost = compute_cost(
        totals["prompt_tokens"], totals["completion_tokens"], pricing,
    )
    per_provider = []
    if active:
        per_provider.append({
            "provider": active.get("id", ""),
            "model": active.get("model", ""),
            "prompt_tokens": totals["prompt_tokens"],
            "completion_tokens": totals["completion_tokens"],
            "cost_usd": estimated_cost,
        })

    recent = timeline[-7:]
    forecast_monthly = 0.0
    if recent and pricing:
        daily_cost = sum(
            compute_cost(d["prompt_tokens"], d["completion_tokens"], pricing)
            for d in recent
        ) / len(recent)
        forecast_monthly = round(daily_cost * 30, 4)

    return {
        "kpis": {
            "total_tokens": total_tokens,
            "prompt_tokens": totals["prompt_tokens"],
            "completion_tokens": totals["completion_tokens"],
            "cached_tokens": cached_tokens,
            "cache_hit_pct": cache_hit_pct,
            "estimated_cost_usd": estimated_cost,
            "forecast_monthly_usd": forecast_monthly,
            "decision_rows": rows_total,
            "from": from_ts,
            "to": to_ts,
        },
        "timeline": timeline,
        "per_provider": per_provider,
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
            config=(ctx or {}).get("config"),
        )
        await ws.send_json({"type": "usage.snapshot", **snap})
        return True
    return False

# SPDX-License-Identifier: MIT
"""WS dispatcher for Usage page: token rollups + cost."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import WebSocket


def _default_db() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "memory.db"


def _resolve_db(ctx: dict[str, Any] | None) -> Path:
    if ctx and ctx.get("db_path"):
        return Path(ctx["db_path"])
    return _default_db()


def _build_snapshot(db_path: Path, from_ts: str, to_ts: str,
                    config: Any = None) -> dict[str, Any]:
    from src.memory.decision_log import DecisionLog
    from src.memory.integrations import (
        get_token_usage_by_provider,
        get_token_usage_timeline,
        get_token_usage_totals,
    )

    totals = get_token_usage_totals(from_ts=from_ts, to_ts=to_ts, db_path=db_path)

    log = DecisionLog(db_path=db_path)
    rows_total = log.get_total()
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

    timeline = get_token_usage_timeline(from_ts=from_ts, to_ts=to_ts, db_path=db_path)

    per_provider = []
    try:
        per_provider = get_token_usage_by_provider(
            from_ts=from_ts, to_ts=to_ts, db_path=db_path,
        )
    except Exception:
        per_provider = []

    recent = timeline[-7:]
    forecast_monthly = 0.0
    if recent:
        forecast_monthly = round(
            sum(d["cost_usd"] for d in recent) / len(recent) * 30, 4,
        )

    return {
        "kpis": {
            "total_tokens": totals["total_tokens"],
            "prompt_tokens": totals["input_tokens"],
            "completion_tokens": totals["output_tokens"],
            "cached_tokens": totals["cache_read_tokens"],
            "cache_creation_tokens": totals["cache_creation_tokens"],
            "cache_hit_pct": totals["cache_hit_pct"],
            "estimated_cost_usd": round(totals["cost_usd"], 10),
            "forecast_monthly_usd": forecast_monthly,
            "decision_rows": rows_total,
            "requests": totals["requests"],
            "from": from_ts,
            "to": to_ts,
        },
        "timeline": timeline,
        "per_provider": per_provider,
        "per_tool": per_tool,
    }


async def dispatch(ws: WebSocket, msg: dict[str, Any], ctx: dict[str, Any] | None = None) -> bool:
    if msg.get("type") == "usage.range":
        db = _resolve_db(ctx)
        snap = _build_snapshot(
            db,
            from_ts=str(msg.get("from", "")),
            to_ts=str(msg.get("to", "")),
            config=(ctx or {}).get("config"),
        )
        await ws.send_json({"type": "usage.snapshot", **snap})
        return True
    return False
# SPDX-License-Identifier: MIT
"""WS dispatcher for Insights page: aggregated KPIs + tool stats + recent decisions."""

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


def _build_snapshot(db_path: Path) -> dict[str, Any]:
    from src.memory.decision_log import DecisionLog

    log = DecisionLog(db_path=db_path)
    totals = log.get_token_totals()
    rows_total = log.get_total()
    recent = log.get_recent(limit=10)
    tool_stats = log.get_stats(min_uses=1)

    successes = sum(t.get("successes", 0) for t in tool_stats)
    success_rate = (
        round(100.0 * successes / rows_total, 1) if rows_total else 0.0
    )

    kpis = {
        "total_decisions": rows_total,
        "success_rate_pct": success_rate,
        "total_tokens": totals["total_tokens"],
        "total_prompt_tokens": totals["prompt_tokens"],
        "total_completion_tokens": totals["completion_tokens"],
        "total_cached_tokens": totals["cached_tokens"],
    }

    md_lines: list[str] = ["## Active Strategies", ""]
    try:
        from src.memory.reflection import ReflectionStore

        store = ReflectionStore(db_path=db_path)
        recent_refl = store.list_recent(limit=8)
        if recent_refl:
            for r in recent_refl:
                strat = (r.get("suggested_strategy") or "").strip()
                if not strat:
                    continue
                outcome = r.get("outcome", "unknown")
                md_lines.append(f"- **[{outcome}]** {strat}")
        else:
            md_lines.append("_No reflections recorded yet._")
    except Exception:
        md_lines.append("_Reflection data unavailable._")

    return {
        "kpis": kpis,
        "tool_stats": tool_stats,
        "active_strategies_markdown": "\n".join(md_lines),
        "recent_decisions": [r.to_dict() for r in recent],
    }


async def dispatch(ws: WebSocket, msg: dict[str, Any], ctx: dict[str, Any] | None = None) -> bool:
    if msg.get("type") == "insights.get":
        db = _resolve_db(ctx)
        snapshot = _build_snapshot(db)
        await ws.send_json({"type": "insights.snapshot", **snapshot})
        return True
    return False

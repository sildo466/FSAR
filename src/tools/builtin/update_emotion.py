# SPDX-License-Identifier: Apache-2.0
"""LLM-callable tool for updating character emotion state (spec D17).

Each call must provide a non-empty `reason` (audit log). Per-metric delta
is capped at MAX_DELTA_PERCENT * (max - min).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.tools.registry import Tool
from src.utils.logger import logger

MAX_DELTA_PERCENT = 0.1
_MAX_REASON_LEN = 200


class UpdateEmotionError(Exception):
    pass


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _resolve_repo_path() -> Path:
    from src.utils.fsar_config import FsarConfig
    return Path(FsarConfig().memory_sqlite_path)


def _get_default_character_id() -> int | None:
    """Look up the default character when LLM did not supply character_id."""
    from src.memory.cards import CardRepo
    repo = CardRepo(_resolve_repo_path())
    ch = repo.get_default_character()
    return ch.id if ch else None


def update_emotion(
    card_repo,
    character_id: int,
    deltas: dict[str, float],
    reason: str,
    session_id: str | None = None,
) -> dict[str, Any]:
    if not reason or not reason.strip():
        raise UpdateEmotionError("reason is required and must be non-empty")
    if len(reason) > _MAX_REASON_LEN:
        raise UpdateEmotionError(f"reason exceeds {_MAX_REASON_LEN} chars")

    state = dict(card_repo.get_emotion_state(character_id))
    schema = {m["key"]: m for m in card_repo.get_emotion_schema(character_id)}
    if not schema:
        raise UpdateEmotionError(f"character {character_id} has no emotion schema")

    audit_ids: list[int] = []
    updated: dict[str, float] = {}
    for key, delta in deltas.items():
        if key not in schema:
            raise UpdateEmotionError(f"metric {key!r} not in schema")
        m = schema[key]
        lo, hi = m["min"], m["max"]
        max_delta = MAX_DELTA_PERCENT * (hi - lo)
        delta = float(delta)
        if delta > max_delta:
            delta = max_delta
        elif delta < -max_delta:
            delta = -max_delta
        old = state.get(key, float(m["initial"]))
        new = _clamp(old + delta, lo, hi)
        updated[key] = new
        aid = card_repo.append_emotion_audit(
            character_id=character_id, session_id=session_id,
            metric_key=key, old_value=old, new_value=new,
            reason=reason, source="update_emotion",
        )
        audit_ids.append(aid)
        state[key] = new

    if not updated:
        raise UpdateEmotionError("no deltas provided")

    card_repo.set_emotion_state(character_id, state)
    return {"updated": updated, "audit_ids": audit_ids}


class UpdateEmotionTool(Tool):
    """LLM-callable wrapper around `update_emotion()` (spec D17)."""

    @property
    def name(self) -> str:
        return "update_emotion"

    @property
    def description(self) -> str:
        return (
            "Update emotion variables for the current character. "
            "Each delta is capped at 10% of the metric's range per call. "
            "Static metrics (empathy/playfulness/formality) cannot be modified. "
            "Always provide a non-empty `reason` (≤200 chars) for the audit log."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "character_id": {
                    "type": "integer",
                    "description": (
                        "Target character id. Omit to update the session/default character."
                    ),
                },
                "deltas": {
                    "type": "object",
                    "description": (
                        "Metric → signed delta. "
                        "Allowed keys: affection, trust, mood, energy."
                    ),
                    "properties": {
                        "affection": {"type": "number"},
                        "trust": {"type": "number"},
                        "mood": {"type": "number"},
                        "energy": {"type": "number"},
                    },
                },
                "reason": {
                    "type": "string",
                    "description": "Why this shift is being recorded (audit). Required, ≤200 chars.",
                },
            },
            "required": ["deltas", "reason"],
        }

    @property
    def risk_level(self) -> str:
        return "SAFE"

    async def execute(self, *, deltas: dict[str, float], reason: str,
                      character_id: int | None = None,
                      session_id: str | None = None, **kwargs) -> str:
        from src.memory.cards import CardRepo
        repo = CardRepo(_resolve_repo_path())
        cid = character_id if character_id is not None else _get_default_character_id()
        if cid is None:
            return "[ERROR] no character_id provided and no default character found"
        try:
            result = update_emotion(repo, cid, deltas, reason, session_id=session_id)
        except UpdateEmotionError as e:
            return f"[ERROR] {e}"
        logger.info(f"update_emotion: char={cid} deltas={deltas}")
        return json.dumps(result, ensure_ascii=False)

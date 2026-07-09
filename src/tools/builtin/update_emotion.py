# SPDX-License-Identifier: Apache-2.0
"""LLM-callable tool for updating character emotion state (spec D17).

Each call must provide a non-empty `reason` (audit log). Per-metric delta
is capped at MAX_DELTA_PERCENT * (max - min).
"""
from __future__ import annotations

from typing import Any

MAX_DELTA_PERCENT = 0.1
_MAX_REASON_LEN = 200


class UpdateEmotionError(Exception):
    pass


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


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

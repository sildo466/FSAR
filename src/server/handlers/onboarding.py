# SPDX-License-Identifier: Apache-2.0
"""Onboarding WS handler: get_state, complete_step, complete, reset."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket

from src.utils.fsar_config import FsarConfig

logger = logging.getLogger(__name__)

ALL_STEPS = ("provider", "user_card", "character_card")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _compute_current_step(completed_steps: list[str]) -> str | None:
    for s in ALL_STEPS:
        if s not in completed_steps:
            return s
    return None


async def dispatch(ws: WebSocket, msg: dict[str, Any], config: FsarConfig) -> bool:
    """Route onboarding.* WS messages. Returns True if handled."""
    t = msg.get("type")
    if t == "onboarding.get_state":
        await ws.send_json(await onboarding_get_state(config))
        return True
    if t == "onboarding.complete_step":
        try:
            result = await onboarding_complete_step(
                fsar_config=config,
                step=msg.get("step", ""),
                data=msg.get("data"),
            )
            await ws.send_json(result)
        except ValueError as e:
            await ws.send_json({"type": "onboarding.error", "code": "bad_request", "message": str(e)})
        return True
    return False


async def onboarding_get_state(fsar_config: FsarConfig) -> dict:
    """Return current onboarding state derived from fsar.yaml."""
    completed = bool(fsar_config.get("onboarding.completed"))
    completed_steps = fsar_config.get("onboarding.completed_steps") or []
    return {
        "type": "onboarding.state",
        "required": not completed,
        "completed": completed,
        "completed_steps": completed_steps,
        "current_step": _compute_current_step(completed_steps) if not completed else None,
    }


async def onboarding_complete_step(
    fsar_config: FsarConfig, step: str, data: dict | None = None,
) -> dict:
    """Append `step` to onboarding.completed_steps; bump last_step + started_at."""
    if step not in ALL_STEPS:
        raise ValueError(f"unknown step: {step!r}; must be one of {ALL_STEPS}")
    steps = list(fsar_config.get("onboarding.completed_steps") or [])
    if step not in steps:
        steps.append(step)
    fsar_config.patch("onboarding.completed_steps", steps)
    fsar_config.patch("onboarding.last_step", step)
    if not fsar_config.get("onboarding.started_at"):
        fsar_config.patch("onboarding.started_at", _now_iso())
    fsar_config.save()
    return {"type": "onboarding.step_completed", "step": step}
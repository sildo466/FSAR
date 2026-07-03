# SPDX-License-Identifier: Apache-2.0
"""WS dispatcher for risk.respond messages."""

from __future__ import annotations

from typing import Any

from fastapi import WebSocket

from src.security.confirmation import ConfirmResponse
from src.server.risk_bridge import RiskBridge

_RESP_MAP = {
    "y": ConfirmResponse.YES,
    "n": ConfirmResponse.NO,
    "all": ConfirmResponse.ALL,
    "server": ConfirmResponse.SERVER_TRUST,
    "never": ConfirmResponse.NEVER,
}


async def dispatch(bridge: RiskBridge, ws: WebSocket, msg: dict[str, Any]) -> bool:
    if msg.get("type") != "risk.respond":
        return False
    resp = _RESP_MAP.get(msg.get("response", ""))
    if resp is not None:
        bridge.respond(msg["call_id"], resp)
    return True

# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import asyncio

from src.security.confirmation import ConfirmResponse
from src.server.risk_bridge import RiskBridge


def test_risk_bridge_resolves_future_on_response():
    bridge = RiskBridge()

    async def scenario() -> ConfirmResponse:
        fut = asyncio.ensure_future(
            bridge.submit("c1", "tool", "args", "reason", timeout=2.0)
        )
        await asyncio.sleep(0.05)
        bridge.respond("c1", ConfirmResponse.YES)
        return await fut

    result = asyncio.run(scenario())
    assert result == ConfirmResponse.YES


def test_risk_bridge_timeout_returns_no():
    bridge = RiskBridge()

    async def scenario() -> ConfirmResponse:
        return await bridge.submit("c1", "tool", "args", "reason", timeout=0.1)

    result = asyncio.run(scenario())
    assert result == ConfirmResponse.NO

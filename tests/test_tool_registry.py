# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import asyncio

from src.tools.registry import Tool, ToolRegistry


class NamedTool(Tool):
    @property
    def name(self) -> str:
        return "named_tool"

    @property
    def description(self) -> str:
        return "Return a supplied name."

    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {"name": {"type": "string"}}}

    @property
    def risk_level(self) -> str:
        return "SAFE"

    async def execute(self, *, name: str, **kwargs) -> str:
        return name


def test_registry_allows_tool_argument_named_name():
    registry = ToolRegistry(auto_track=False)
    registry.register(NamedTool())

    result = asyncio.run(registry.execute("named_tool", name="guizang-ppt-skill"))

    assert result == "guizang-ppt-skill"

"""RouterTool — the only entry point a character needs to discover abilities."""

from __future__ import annotations

from src.core import router_map
from src.tools.registry import Tool

_HIT_PREFIX = "__UNLOCK__:"

_MISS_MESSAGE = "You try, but this way does not seem to open. Try different words?"
_ERROR_MESSAGE = "You try, but nothing happens this time."


class RouterTool(Tool):
    """Character-mode meta-tool: express intent, system opens matching tools."""

    modes = ("character",)

    @property
    def name(self) -> str:
        return "router"

    @property
    def description(self) -> str:
        return (
            "When you want to do something, name your intent with a few keywords "
            "(in Chinese or English) to see whether the way is open. If it is not, "
            "try different words. Never invent abilities that were never opened to you."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "keywords": {
                    "type": "string",
                    "description": (
                        "A few Chinese or English keywords describing what you want to do."
                    ),
                },
            },
            "required": ["keywords"],
        }

    @property
    def risk_level(self) -> str:
        return "SAFE"

    async def execute(self, *, keywords: str = "", **kwargs) -> str:
        try:
            unlocked = router_map.match_intent(keywords or "")
        except Exception:
            return _ERROR_MESSAGE
        if not unlocked:
            return _MISS_MESSAGE
        return f"{_HIT_PREFIX}{','.join(unlocked)}\n{router_map.unlock_description(unlocked)}"

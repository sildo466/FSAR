"""FSAR Computer Use tools — wrap the cua Python library as registered tools.

Uses ``cua.Localhost`` which delegates to ``cua_auto`` (pynput + pywinctl + pillow),
so no cua-driver daemon or hardcoded binary path is required. A single
``Localhost`` connection is lazily created on first use and reused across calls.
"""

from __future__ import annotations

import asyncio
import base64
from typing import Any

from src.tools.registry import Tool
from src.utils.logger import logger


_host: Any | None = None
_host_lock = asyncio.Lock()


async def _get_host() -> Any:
    global _host
    if _host is not None:
        return _host
    async with _host_lock:
        if _host is None:
            from cua import Localhost
            logger.info("cu: connecting to Localhost via cua-auto")
            _host = await Localhost.connect()
    return _host


async def _close_host() -> None:
    global _host
    if _host is None:
        return
    try:
        await _host.disconnect()
    except Exception as e:
        logger.debug(f"cu: disconnect error (ignored): {e}")
    finally:
        _host = None


class CuScreenshotTool(Tool):
    """Capture the current screen as a base64-encoded PNG."""

    @property
    def name(self) -> str:
        return "cu_screenshot"

    @property
    def description(self) -> str:
        return ("Capture the current screen and return it as base64 PNG. "
                "Use this to see what's on screen before clicking or typing.")

    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {}, "required": []}

    @property
    def risk_level(self) -> str:
        return "LOW"

    async def execute(self, **kwargs) -> str:
        host = await _get_host()
        png = await host.screen.screenshot()
        return base64.b64encode(png).decode("ascii")


class CuScreenSizeTool(Tool):
    """Return the current screen size as (width, height) in pixels."""

    @property
    def name(self) -> str:
        return "cu_screen_size"

    @property
    def description(self) -> str:
        return "Return the current screen size as (width, height) in pixels."

    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {}, "required": []}

    @property
    def risk_level(self) -> str:
        return "LOW"

    async def execute(self, **kwargs) -> str:
        host = await _get_host()
        w, h = await host.screen.size()
        return f"{w},{h}"


class CuActiveWindowTool(Tool):
    """Return the title of the currently focused window."""

    @property
    def name(self) -> str:
        return "cu_active_window"

    @property
    def description(self) -> str:
        return "Return the title of the currently focused (foreground) window."

    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {}, "required": []}

    @property
    def risk_level(self) -> str:
        return "LOW"

    async def execute(self, **kwargs) -> str:
        host = await _get_host()
        return await host.window.get_active_title()


class CuClickTool(Tool):
    """Click at screen coordinates (x, y)."""

    @property
    def name(self) -> str:
        return "cu_click"

    @property
    def description(self) -> str:
        return ("Click at screen pixel coordinates (x, y). "
                "Use cu_screenshot first to see where to click. "
                "Coordinates are absolute screen pixels (0,0 = top-left).")

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "X pixel coordinate on screen."},
                "y": {"type": "integer", "description": "Y pixel coordinate on screen."},
                "button": {
                    "type": "string",
                    "enum": ["left", "right", "middle"],
                    "default": "left",
                    "description": "Mouse button to click.",
                },
            },
            "required": ["x", "y"],
        }

    @property
    def risk_level(self) -> str:
        return "HIGH"

    async def execute(self, x: int = 0, y: int = 0, button: str = "left", **kwargs) -> str:
        host = await _get_host()
        await host.mouse.click(int(x), int(y), button=button)
        return f"clicked ({x},{y}) {button}"


class CuDoubleClickTool(Tool):
    """Double-click at screen coordinates (x, y)."""

    @property
    def name(self) -> str:
        return "cu_double_click"

    @property
    def description(self) -> str:
        return "Double-click at screen pixel coordinates (x, y)."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "X pixel coordinate on screen."},
                "y": {"type": "integer", "description": "Y pixel coordinate on screen."},
            },
            "required": ["x", "y"],
        }

    @property
    def risk_level(self) -> str:
        return "HIGH"

    async def execute(self, x: int = 0, y: int = 0, **kwargs) -> str:
        host = await _get_host()
        await host.mouse.double_click(int(x), int(y))
        return f"double-clicked ({x},{y})"


class CuScrollTool(Tool):
    """Scroll the mouse wheel at screen coordinates (x, y)."""

    @property
    def name(self) -> str:
        return "cu_scroll"

    @property
    def description(self) -> str:
        return ("Scroll the mouse wheel at screen pixel coordinates (x, y). "
                "Positive scroll_y scrolls down, negative scrolls up.")

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "X pixel coordinate on screen."},
                "y": {"type": "integer", "description": "Y pixel coordinate on screen."},
                "scroll_y": {
                    "type": "integer",
                    "default": 3,
                    "description": "Vertical scroll ticks (positive = down).",
                },
                "scroll_x": {
                    "type": "integer",
                    "default": 0,
                    "description": "Horizontal scroll ticks (positive = right).",
                },
            },
            "required": ["x", "y"],
        }

    @property
    def risk_level(self) -> str:
        return "HIGH"

    async def execute(self, x: int = 0, y: int = 0,
                      scroll_y: int = 3, scroll_x: int = 0, **kwargs) -> str:
        host = await _get_host()
        await host.mouse.scroll(int(x), int(y), scroll_x=int(scroll_x), scroll_y=int(scroll_y))
        return f"scrolled ({x},{y}) dy={scroll_y} dx={scroll_x}"


class CuTypeTool(Tool):
    """Type text into the currently focused input field."""

    @property
    def name(self) -> str:
        return "cu_type"

    @property
    def description(self) -> str:
        return ("Type text into the currently focused input field. "
                "Click the target field first, then call this. "
                "Use cu_keypress for shortcuts like ctrl+c.")

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to type."},
            },
            "required": ["text"],
        }

    @property
    def risk_level(self) -> str:
        return "HIGH"

    async def execute(self, text: str = "", **kwargs) -> str:
        host = await _get_host()
        await host.keyboard.type(text)
        return f"typed {len(text)} chars"


class CuKeypressTool(Tool):
    """Press a key or key combination."""

    @property
    def name(self) -> str:
        return "cu_keypress"

    @property
    def description(self) -> str:
        return ("Press a key or key combination. "
                "Pass a single key like 'enter' or 'escape', "
                "or a list for a chord like ['ctrl', 'c'].")

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "keys": {
                    "description": "A single key name (e.g. 'enter') or a list for a chord (e.g. ['ctrl','c']).",
                    "oneOf": [
                        {"type": "string"},
                        {"type": "array", "items": {"type": "string"}},
                    ],
                },
            },
            "required": ["keys"],
        }

    @property
    def risk_level(self) -> str:
        return "HIGH"

    async def execute(self, keys=None, **kwargs) -> str:
        host = await _get_host()
        if keys is None:
            return "Error: keys is required"
        await host.keyboard.keypress(keys)
        return f"pressed {keys}"
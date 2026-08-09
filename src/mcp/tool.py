"""FSAR MCP Tool adapter — wraps a remote MCP tool as a local Tool instance.

The MCP server runs out-of-process (stdio subprocess or SSE endpoint). We turn
each tool it exposes into a `src.tools.registry.Tool` so it slots into the
existing registry + RiskEngine + audit pipeline with zero changes.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from src.tools.registry import Tool

if TYPE_CHECKING:
    from src.mcp.client import MCPClient


def _format_result(result: Any) -> str:
    """Serialize MCP CallToolResult into a string the LLM can read.

    MCP returns a list of content blocks (TextContent / ImageContent / etc.).
    We concatenate text blocks and mention non-text blocks by type so the LLM
    sees what happened without us having to invent a format.
    """
    content = getattr(result, "content", None) or []
    parts: list[str] = []
    for block in content:
        btype = getattr(block, "type", "?")
        if btype == "text":
            parts.append(getattr(block, "text", ""))
        elif btype == "image":
            mime = getattr(block, "mimeType", "image")
            parts.append(f"[image: {mime}, data omitted]")
        elif btype == "audio":
            parts.append(f"[audio omitted]")
        elif btype == "resource_link":
            parts.append(f"[resource: {getattr(block, 'uri', '?')}]")
        elif btype == "resource":
            res = getattr(block, "resource", None)
            text = getattr(res, "text", "") if res else ""
            parts.append(text or f"[embedded resource]")
        else:
            parts.append(f"[{btype} block]")
    text = "\n".join(p for p in parts if p)
    if not text and getattr(result, "structuredContent", None):
        text = json.dumps(result.structuredContent, ensure_ascii=False)
    if getattr(result, "isError", False):
        text = f"[MCP error] {text or 'tool returned isError=true'}"
    return text or "(no content)"


class MCPTool(Tool):
    """Adapter: one MCP tool → one FSAR Tool.

    Names are namespaced as `mcp__{server}__{tool}` to avoid colliding with
    built-in tools and other servers' tools.
    """

    def __init__(
        self,
        server_name: str,
        tool_def: Any,
        client: "MCPClient",
        risk_level: str = "HIGH",
    ):
        self._server = server_name
        self._def = tool_def
        self._client = client
        self._risk_level = risk_level

    # --- Tool ABC ---

    @property
    def name(self) -> str:
        return f"mcp__{self._server}__{self._def.name}"

    @property
    def description(self) -> str:
        raw = self._def.description or ""
        title = getattr(self._def, "title", None)
        prefix = f"[MCP server '{self._server}']"
        if title and title != self._def.name:
            return f"{prefix} {title} — {raw}".strip(" —")
        return f"{prefix} {raw}".strip()

    @property
    def parameters(self) -> dict:
        schema = self._def.inputSchema or {"type": "object", "properties": {}}
        # MCP schemas already follow JSON Schema; pass through as-is.
        if "type" not in schema:
            schema["type"] = "object"
        return schema

    @property
    def risk_level(self) -> str:
        return self._risk_level

    @property
    def server_name(self) -> str:
        return self._server

    @property
    def original_name(self) -> str:
        return self._def.name

    async def execute(self, **kwargs) -> str:
        result = await self._client.call_tool(self._def.name, kwargs)
        return _format_result(result)
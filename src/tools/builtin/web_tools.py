"""FSAR web search and webpage reading tools."""

from __future__ import annotations

from src.mcp.client import MCPClient
from src.tools.registry import Tool
from src.utils.logger import logger


EXA_MCP_URL = "https://mcp.exa.ai/mcp"


async def _call_exa(tool_name: str, arguments: dict) -> str:
    from src.utils.config import get_config
    config = get_config()
    client = MCPClient(name="exa", command="", url=EXA_MCP_URL, config=config)
    try:
        await client.start()
        result = await client.call_tool(tool_name, arguments)
        text = "\n".join(
            getattr(block, "text", "")
            for block in (getattr(result, "content", None) or [])
            if getattr(block, "type", None) == "text"
        ).strip()
        if getattr(result, "isError", False):
            raise RuntimeError(text or "Exa returned an error")
        return text or "(no content)"
    finally:
        await client.stop()


class WebSearchTool(Tool):
    """Search the public web through Exa's MCP service."""

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return (
            "Search the public web for current information. Returns source titles, URLs, "
            "and excerpts; treat excerpts as source material and verify important claims."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "A specific natural-language description of what to find",
                },
                "num_results": {
                    "type": "integer",
                    "default": 5,
                    "description": "Number of results to return (1-10)",
                },
            },
            "required": ["query"],
        }

    @property
    def risk_level(self) -> str:
        return "SAFE"

    async def execute(self, query: str, num_results: int = 5, **kwargs) -> str:
        query = query.strip()
        if not query:
            return "Error searching: query must not be empty"

        try:
            from src.utils.config import get_config
            result = await _call_exa(
                "web_search_exa",
                {"query": query, "numResults": min(max(num_results, 1), 10)},
            )
            if result == "(no content)":
                return f"No results found for: {query}"
            return (
                f"Search results for: {query}\n\n{result}\n\n"
                "Note: These are excerpts from the linked sources, not independently verified facts."
            )
        except Exception as exc:
            logger.error(f"Web search failed: {exc}")
            return f"Error searching the web: {exc}"


class WebFetchTool(Tool):
    """Read webpage content through Exa's MCP service."""

    @property
    def name(self) -> str:
        return "web_fetch"

    @property
    def description(self) -> str:
        return "Fetch a webpage and return its readable content with source metadata."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "HTTP or HTTPS URL to fetch",
                },
                "max_length": {
                    "type": "integer",
                    "default": 5000,
                    "description": "Maximum characters to return",
                },
            },
            "required": ["url"],
        }

    @property
    def risk_level(self) -> str:
        return "SAFE"

    async def execute(self, url: str, max_length: int = 5000, **kwargs) -> str:
        url = url.strip()
        if not url:
            return "Error fetching: URL must not be empty"
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        max_length = max(max_length, 1)
        try:
            from src.skills.egress import enforce_url
            from src.utils.config import get_config
            config = kwargs.get("_security_config") or get_config()
            enforce_url(url, config)
            result = await _call_exa(
                "web_fetch_exa",
                {"urls": [url], "maxCharacters": max_length},
            )
            return result if result != "(no content)" else "(empty response)"
        except Exception as exc:
            logger.error(f"Web fetch failed: {exc}")
            return f"Error fetching the webpage: {exc}"

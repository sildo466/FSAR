"""Tiny standalone MCP server used for smoke-testing the FSAR MCP client.

Exposes three trivial tools over stdio:
    echo    — echo back its argument
    add     — sum two numbers
    fail    — return an error (to verify isError handling)

Run directly:  python tests/mcp_mock_server.py
The FSAR client connects to it via stdio_client.
"""

from __future__ import annotations

import asyncio
import sys

import mcp.server.stdio
import mcp.types as types
from mcp.server import Server
from mcp.server.lowlevel import NotificationOptions


server = Server("fsar-test-mock")


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="echo",
            description="Return the given text unchanged.",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to echo back."},
                },
                "required": ["text"],
            },
        ),
        types.Tool(
            name="add",
            description="Add two integers and return the sum.",
            inputSchema={
                "type": "object",
                "properties": {
                    "a": {"type": "integer"},
                    "b": {"type": "integer"},
                },
                "required": ["a", "b"],
            },
        ),
        types.Tool(
            name="fail",
            description="Always return an error (for testing error handling).",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[types.ContentBlock]:
    if name == "echo":
        text = arguments.get("text", "")
        return [types.TextContent(type="text", text=f"echo: {text}")]
    if name == "add":
        try:
            total = int(arguments.get("a", 0)) + int(arguments.get("b", 0))
            return [types.TextContent(type="text", text=str(total))]
        except (TypeError, ValueError) as e:
            return [types.TextContent(type="text", text=f"add error: {e}")]
    if name == "fail":
        return [types.TextContent(type="text", text="intentional failure"), types.TextContent(type="text", text="use this to test error path")]
    raise ValueError(f"unknown tool: {name}")


async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)
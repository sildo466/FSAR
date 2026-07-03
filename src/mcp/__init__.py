"""FSAR MCP client — connect to external Model Context Protocol servers.

Public API:
    MCPManager — load config, start servers, register tools into a ToolRegistry
    MCPClient  — single-server subprocess wrapper
    MCPTool    — adapter that wraps an MCP tool as a src.tools.registry.Tool
"""

from src.mcp.client import MCPClient
from src.mcp.manager import MCPManager
from src.mcp.tool import MCPTool

__all__ = ["MCPClient", "MCPManager", "MCPTool"]
# mcp — Model Context Protocol client

> Language: [中文](mcp.md) | English · Back to [module index](README.en.md)

Connects to external MCP servers.

| File | Description |
|---|---|
| `manager.py` | `MCPManager`: multi-server lifecycle; registers their tools into a `ToolRegistry`; review/verify; shut down. |
| `client.py` | Single-server wrapper (stdio subprocess and streamable HTTP). |
| `tool.py` | `MCPTool`: wraps a remote MCP tool as a local `Tool` (carries `server_name` for server-level trust). |
| `cli.py` | `python -m src.mcp.cli` manages MCP registrations (writes into `fsar.yaml`). |
| `presets.py` | Built-in MCP server presets. |

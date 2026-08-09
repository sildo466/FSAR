# mcp — Model Context Protocol 客户端

> 语言：中文 | [English](mcp.en.md) · 返回 [模块索引](README.md)

连接外部 MCP 服务器。

| 文件 | 说明 |
|---|---|
| `manager.py` | `MCPManager`：多服务器生命周期，注册其工具进 `ToolRegistry`，审阅/验证、关闭。 |
| `client.py` | 单服务器封装（stdio 子进程与 streamable HTTP）。 |
| `tool.py` | `MCPTool`：把远端 MCP 工具包装为本地 `Tool`（携带 `server_name` 供服务器级信任）。 |
| `cli.py` | `python -m src.mcp.cli` 管理 MCP 注册（写入 `fsar.yaml`）。 |
| `presets.py` | 内置 MCP 服务器预设。 |

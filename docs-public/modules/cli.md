# 终端 TUI 模块（`src/cli/`）

> 语言：中文 | [English](cli.en.md)

终端交互前端。v0.4.0 把早期简单 REPL 升级为全屏 Textual 应用，入口为 `fsar`（pyproject 的 console script，即 `src.cli.tui:main`），也可用 `python -m src.cli.tui`，或带模式参数启动：`fsar agent`（默认） / `fsar character`（入戏模式） / `fsar companion`。

| 文件 | 职责 |
|---|---|
| `tui.py` | 核心 `ChatApp`（Textual App）：聊天主界面、启动摘要、底部状态栏（聊天模式 + 实时上下文占用）、cwd 沙盒绑定、斜杠命令分发 |
| `tui_commands.py` | 命令预测系统：UI 命令表 + 从服务器 handler 注册表实时派生的引擎命令 + 已安装 skill 的 `/use <name>` 动态条目 |
| `tui_screens.py` | 模态屏幕：模型 / 角色卡 / 用户卡选择、档位、effort、权限设置等 |
| `tui_widgets.py` | 输入框、消息气泡等自绘组件 |

TUI 与 GUI 共用同一个 `ChatEngine`（`src/server/chat_engine.py`），共享 `~/.fsar/` 数据、内置工具、安全闸门与 MCP 会话；日志写入 `~/.fsar/data/logs/fsar_cli_*.log`，终端内只保留 Textual 界面输出。
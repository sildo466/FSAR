# tools — 工具系统

> 语言：中文 | [English](tools.en.md) · 返回 [模块索引](README.md)

以 OpenAI function-calling 格式表达的、可被 LLM 调用的工具注册表。

| 文件 | 说明 |
|---|---|
| `registry.py` | `Tool` 抽象基类与 `ToolRegistry`（注册/发现/生成 schema/执行）。 |
| `__init__.py` | `create_default_registry(config)` 注册全部内置工具（规范入口）。 |
| `builtin/` | `run_command`（shell/PowerShell，带超时）、`file_ops`（读/写/列/移/删）、`edit`（精确替换）、`process`（后台进程）、`web_tools`（搜索/抓取）、`app_control`（启动应用）、`image_analyze` / `pdf_analyze`、`experience_tools` + `experience_import`、`update_emotion`、`skill_tool` / `skill_folder`、`cu_tools`（Computer Use：截图/点击/双击/滚动/输入/按键，封装 cua 库）。 |

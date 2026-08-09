# tools — the tool system

> Language: [中文](tools.md) | English · Back to [module index](README.en.md)

A registry of LLM-callable tools expressed in OpenAI function-calling format.

| File | Description |
|---|---|
| `registry.py` | The `Tool` abstract base and `ToolRegistry` (register/discover/emit schema/execute). |
| `__init__.py` | `create_default_registry(config)` registers all built-ins (canonical entry). |
| `builtin/` | `run_command` (shell/PowerShell, with timeout), `file_ops` (read/write/list/move/delete), `edit` (precise replacement), `process` (background processes), `web_tools` (search/fetch), `app_control` (launch apps), `image_analyze` / `pdf_analyze`, `experience_tools` + `experience_import`, `update_emotion`, `skill_tool` / `skill_folder`, `cu_tools` (Computer Use: screenshot/click/double-click/scroll/type/keypress, wrapping the cua library). |

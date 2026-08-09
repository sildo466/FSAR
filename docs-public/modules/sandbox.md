# sandbox — 工作区沙盒策略

> 语言：中文 | [English](sandbox.en.md) · 返回 [模块索引](README.md)

每个会话绑定一个工作区目录；本包判定路径/命令是否越界。

| 文件 | 说明 |
|---|---|
| `workspace_gate.py` | `WorkspaceGate.validate_path()` / `command_verdicts()` → `PathVerdict`（proceed/deny/confirm_escape）；`SessionAllowCache` 记忆会话级逃逸授权；`extract_path_tokens()` 从命令中提取路径。 |
| `hardline.py` | 无条件命令安全地板（永不可被用户权限覆盖）。 |
| `paths.py` | 路径归一化与工作区包含判定。 |
| `sensitive.py` | 始终需确认的敏感位置 + 文件读取黑名单。 |
| `tool_guard.py` | 工具内部共享的第二道沙盒守卫。 |

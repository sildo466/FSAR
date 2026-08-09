# 模块介绍

> 语言：中文 | [English](README.en.md)

FSAR 后端代码位于 `src/`，前端位于 `frontend/`。本目录按模块分页，说明各自的职责与关键文件。

> 约定：`prompt_archive.py`、`episodic_shim.py` 等属于遗留/兼容代码，下文不单列。

## 后端 `src/`

| 模块 | 定位 |
|---|---|
| [server](server.md) | WebSocket 服务与 GUI 聊天引擎 |
| [core](core.md) | 智能体基础设施 |
| [memory](memory.md) | 记忆系统 |
| [tools](tools.md) | 工具系统 |
| [security](security.md) | 安全层 |
| [sandbox](sandbox.md) | 工作区沙盒策略 |
| [skills](skills.md) | 受审阅的本地技能执行 |
| [social](social.md) | 社交平台桥接 |
| [providers](providers.md) | LLM / ASR / TTS 适配器 |
| [mcp](mcp.md) | Model Context Protocol 客户端 |
| [utils](utils.md) | 横切基础设施 |
| [scheduler](scheduler.md) | 定时任务 |

## 前端与数据目录

- [frontend](frontend.md) — Vite + React 前端应用（Tauri 桌面壳）
- [layout](layout.md) — `data/` 与 `config/` 的随库内容与运行时数据库

## 延伸阅读

- [项目总览](../overview.md) · [配置详解](../configuration.md) · [开发教程](../development.md)
- [`SECURITY.md`](../../SECURITY.md) · [`CONTRIBUTING.md`](../../CONTRIBUTING.md)

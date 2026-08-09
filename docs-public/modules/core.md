# core — 智能体基础设施

> 语言：中文 | [English](core.en.md) · 返回 [模块索引](README.md)

CLI 与 GUI 共享的智能体循环构件：提示词、persona 组装、能力档位、运行态。

| 文件 | 说明 |
|---|---|
| `agent_tiers.py` | `TierProfile` 与 `TIER_ORDER = (low, medium, high, xhigh, max, ultra)`；`get_tier_profile()` 给出每档的最大工具轮数、子代理、反思、校验、压缩阈值等。 |
| `agent_runtime.py` | 每次运行的临时状态：`AgentRecord`、`AgentRunState`、`AgentLoopResult`。 |
| `prompts.py` | 共享系统提示词（CLI/GUI 单源），含安装 MCP/技能的脚本化流程。 |
| `persona.py` | 组装 `[CHARACTER CARD] / [EXAMPLE DIALOGUES] / [USER CARD] / [EMOTION STATE]` 前缀块。 |
| `strategy_injector.py` | 合成 `## Learned Strategies` 块。 |
| `experience_injector.py` | 构建 `## Experiences` 索引块。 |
| `context_compaction.py` | 长任务的结构感知上下文压缩。 |
| `event_bus.py` | 进程内事件总线（`EventType` 枚举），调度器经它发事件。 |
| `formula_engine.py` | 角色卡情绪公式的安全算术求值器（仅 `+ - * /`、数字、变量、括号，带 clamp）。 |

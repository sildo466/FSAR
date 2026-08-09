# 项目总览

> 语言：中文 | [English](overview.en.md)

**FSAR**（Fully Self-evolving AI Companion）是一个**本地优先**的 AI 伴侣：对话、记忆、决策与工具全部运行在你自己的机器上，存于 `~/.fsar/` 的 SQLite 数据库里，不上传到任何 FSAR 服务器。它属于用户，而不是某个供应商。

名字本身就是设计契约：**F**aithful（忠实）· **S**afe（安全）· **A**daptive（自适应）· **R**eflective（反思）。

## 四大支柱

- **Faithful（忠实）** — FSAR 就是你配置的那个角色（角色卡：名字、性格、场景、情绪状态），对着你描述的用户卡说话，不会退化成"通用助手"。
- **Safe（安全）** — 每个工具调用都穿过分层检查：硬编码的 hardline 守卫在最前面拦下破坏性命令（`rm -rf /`、`shutdown`、`mkfs`）；风险引擎把每个工具分为 SAFE/LOW/MEDIUM/HIGH/CRITICAL；工作区门禁限制文件访问范围；子进程环境清洗器在运行技能前剥掉 API key 与令牌。详见 [`SECURITY.md`](../SECURITY.md)。
- **Adaptive（自适应）** — 每次工具调用都被记录。策略注入器从决策日志与用户画像合成一段 `## Learned Strategies` 注入系统提示词；经验存储把过程性知识持久化，让"这次会话装的 MCP 服务器"成为"下次会话的召回"。
- **Reflective（反思）** — 三种反思模式（每任务 / 失败时 / 空闲批量）重读对话并更新用户画像：显式偏好（如"用 VSCode"）、推断特征（如"常在晚上写代码"）、行为模式。下次会话开场即带上这些上下文。

## 它能做什么

- 运行 shell 命令（Windows 上 PowerShell，其它平台 bash），带 hardline 守卫
- 在受限工作区内读、写、搜索文件
- 通过沙盒别名表打开应用与网址
- 通过免费的 [Exa MCP](https://mcp.exa.ai) 搜索与抓取网页（无需 API key）
- 本地分析图像与 PDF
- 操作你的电脑（Computer Use / cua）：截图、点击、输入、按键——单独 gated
- 把新技能作为 SQLite 经验行持久化（一次安装，多次召回）
- 通过 Telegram、飞书、微信收发消息

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.12+，FastAPI + WebSocket |
| 前端 | Tauri 2 + React + TypeScript（Vite） |
| 存储 | SQLite（`memory.db` 等）+ ChromaDB（语义向量） |
| 模型 | OpenAI / Anthropic / Google / DeepSeek / 任意 OpenAI 兼容端点 / Ollama / LM Studio |
| CLI 入口 | `main.py`（控制台脚本 `fsar`） |

## 架构鸟瞰

```
                 ┌───────────────────────────────────────────┐
                 │  前端 (Tauri 2 / React)  frontend/dist      │
                 │  聊天 / 卡片 / 记忆 / 反思 / 设置 / 向导      │
                 └───────────────┬───────────────────────────┘
                                 │ WebSocket (JSON) + HTTP  /ws
                 ┌───────────────▼───────────────────────────┐
                 │  src/server   FastAPI 应用 + ChatEngine     │
                 │  handlers/ (~23 个消息路由)  RiskBridge      │
                 └───────────────┬───────────────────────────┘
                                 │
        ┌───────────────┬────────┴────────┬────────────────┐
        ▼               ▼                 ▼                ▼
   src/core        src/memory        src/tools        src/social
   智能体循环/      短期/长期/语义/    工具注册表 +      Telegram/飞书/
   提示词/注入器    用户画像/反思/经验  内置工具          微信适配器
        │               │                 │
        │        ┌──────┴─────────────────┴──────────┐
        │        ▼                                    ▼
        │   src/security  风险引擎/权限/确认/审计   src/sandbox  hardline/工作区门禁/敏感路径
        │        │                                    │
        └────────┴──────────┬─────────────────────────┘
                            ▼
                    src/skills  技能审阅门禁 + 子进程执行
                    src/mcp     外部 MCP 服务器
                    src/providers  LLM / TTS / ASR 适配器
                    src/utils   配置 / LLM 缓存 / 日志 / 迁移
```

## 一条消息的端到端流程

以 GUI 发来一条聊天消息为例（细节见 `src/server/chat_engine.py`）：

1. **接入** — 前端经 `/ws` 发来 JSON 消息，`ws_server._dispatch` 依次尝试各 handler；`chat.send` 落入 `handlers/chat.py`，派生任务调用 `ChatEngine.handle_send`。
2. **准备** — 确保会话与工作区绑定，解析角色卡，发出 `chat.thinking`。根据内容分流：`/` 前缀走斜杠命令；选择"集成"模型走多模型集成图；`companion` 模式走单轮陪伴；否则进入智能体循环。
3. **组装提示词** — 取智能体档位（`agent.tier`），用 `AGENT_SYSTEM_PROMPT` + 角色/用户卡 persona + `## Learned Strategies` + `## Experiences` 组装系统提示词，装入短期记忆并按上下文窗口裁剪。
4. **智能体循环** — 最多迭代 `max_tool_turns` 轮：按需压缩上下文，经两级缓存调用 LLM；若响应含工具调用则执行（可并行），高阶档位还会做对抗式校验与微反思，直到模型给出无需工具的最终答复。
5. **每次工具调用的安全关卡**（顺序执行，任一拒绝即停止）：
   - **MCP 门禁** — 带 `server_name` 的工具须通过服务器审阅/验证；
   - **沙盒门禁** — `WorkspaceGate` 校验路径/命令；越界触发"沙盒逃逸确认"，等待用户 `deny / allow_once / allow_session / allow_always`；
   - **风险门禁** — `RiskEngine.evaluate` 给出 `proceed / confirm / deny`；需确认时等待前端响应（可授予会话信任 / 信任整个 MCP 服务器 / 永久拒绝）；
   - **执行** — 对 `run_command` 先做网络出口检查与读取黑名单检查，并把工作目录固定在工作区根；
   - **执行后** — 小模型复核结果、脱敏密钥、发出 `chat.tool_result`、写入审计日志。
6. **收尾** — 工具结果回填，循环继续直至成答；保存并流式输出结论（可触发 TTS），按档位运行任务反思、推进空闲反思、懒生成会话标题。

## 数据都在哪

一切关于你的数据都在 `~/.fsar/`：

```
~/.fsar/config/        yaml 配置
~/.fsar/data/
  memory.db            对话、决策、用户画像、经验
  chroma/              语义嵌入
  llm_cache.db         L1/L2 响应缓存
  tts_cache.db         TTS 音频缓存
  scheduler.db         定时任务
  logs/                滚动日志 + audit.log（审计）
```

删除 `~/.fsar/` 即彻底重置。

## 接下来读什么

- [模块介绍](modules/README.md) — 每个源码模块的职责与关键文件
- [配置详解](configuration.md) — `fsar.yaml` 逐项说明
- [编译 / 测试 / 开发教程](development.md)
- [`SECURITY.md`](../SECURITY.md) — 安全机制与漏洞报告
- [`CONTRIBUTING.md`](../CONTRIBUTING.md) — 参与贡献

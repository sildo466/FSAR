# memory — 记忆系统

> 语言：中文 | [English](memory.en.md) · 返回 [模块索引](README.md)

分层记忆（短期 / 长期 / 语义 / 用户画像）+ 反思、召回、经验层、角色/用户卡。多数存于 `data/memory.db`，向量存于 `data/chroma`。召回是带日期的——条目带着自己的年龄，因此角色能说出某件事是多久以前发生的；对这些存储的每一次写入，在落地之前都会做提示词注入筛查。

| 文件 | 说明 |
|---|---|
| `short_term.py` / `long_term.py` | 当前会话上下文窗口 / SQLite 持久化长期记忆。 |
| `session_store.py` | 每会话的元数据与消息持久化。 |
| `semantic.py` | ChromaDB 向量语义记忆。 |
| `user_model.py` | 偏好、习惯、画像。 |
| `recall.py` | `MemoryRecall.recall_for_context()` 统一接口，返回 LLM 友好的上下文块（语义历史 + 偏好 + 模式 + 画像）。 |
| `reflection.py` | `IdleReflector`（空闲巩固）+ `TaskReflector`（每任务）+ `ReflectionStore`，强度 OFF/LOW/MEDIUM/HIGH。 |
| `feedback.py` | RLHF 式消息评分（来自界面 `chat.rate`）。 |
| `decision_log.py` | 每次工具调用的追踪（自演化用），含 contextvars 任务上下文。 |
| `experience_store.py` | 经验层：DB-first 过程性知识，SQLite 表 `experiences` 等；状态 ACTIVE/STALE/ARCHIVED。 |
| `experience_embedding.py` | 对经验与记忆块的按需向量检索。 |
| `embedder.py` + `*_embed.py` | 按配置选择 OpenAI / LM Studio / Ollama 嵌入器。 |
| `cards.py` | 角色卡 / 用户卡 / `CardRepo`，加载 `data/emotion_default.json` 默认情绪公式。 |
| `workspace.py` | 沙盒工作区持久化、会话↔工作区绑定、沙盒审计事件。 |
| `integrations.py` | 递归集成的持久化与图校验（`CycleError` 等）。 |
| `candidates.py` / `judge.py` / `pack.py` | 注入链路：召回结果变成可逐条评判的候选，可选端点按相关性评分，存活者被原子化地打包进一份共享的字符预算。 |
| `rooms.py` / `room_plan.py` | 群聊房间——一个房间是一个实体，恰好持有一条会话——以及房间的计划板。 |
| `patches.py` / `publishes.py` | 等待被查看的补丁，以及已离开项目的记录。 |
| `agent_members.py` / `member_tokens.py` | 作为房间成员的外部 agent，以及"非本机用户"成员的凭证。 |
| `lan_blocklist.py` / `auth_audit.py` | 完全不许触达局域网监听的地址，以及只追加的身份审计。 |
| `idempotency.py` | 局域网 POST 的请求去重。 |

在房间里，一条消息归属于说出它的人，每个角色写回自己的记忆，外加一份房间级记忆。

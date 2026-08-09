# social — 社交平台桥接

> 语言：中文 | [English](social.en.md) · 返回 [模块索引](README.md)

把外部聊天平台接入与 GUI 相同的 `ChatEngine`。

| 文件 | 说明 |
|---|---|
| `channels.py` | 适配器契约：`ChannelAdapter`、`ChannelEvent`、`ReplyTarget`。 |
| `adapters/` | `telegram.py` / `feishu.py` / `wechat.py`。 |
| `router.py` | 入站事件路由进 FSAR（`handle_user_message` companion 补全），出站回复排队；处理静音与会话状态。 |
| `outbox.py` | 持久化出站重试队列。 |
| `state.py` | 社交会话、平台↔会话绑定、适配器游标的 SQLite 持久化。 |
| `manager.py` | `build_router_and_adapters()` / `start_social()` / `stop_social()` 生命周期。 |

# server — WebSocket 服务与 GUI 聊天引擎

> 语言：中文 | [English](server.en.md) · 返回 [模块索引](README.md)

FastAPI 应用、唯一 `/ws` JSON 端点，以及驱动对话的 `ChatEngine`。

| 文件 | 说明 |
|---|---|
| `ws_server.py` | FastAPI 应用入口：首跑把模板复制为 `fsar.yaml`；创建 `RiskBridge`、`ChatEngine`、`WSAuthenticator`；托管 `frontend/dist`；暴露 health、飞书 webhook、微信扫码、头像上传下载、`/ws/token`、技能安装、`/ws/scheduler` 等路由。`start(host, port)` 为服务入口。 |
| `chat_engine.py` | 核心类 `ChatEngine`（复用 CLI 的 LLM/工具/记忆栈跑在 WS 上）；另含 `resolve_chat_model()`、供集成/社交复用的 `handle_user_message()`。 |
| `handlers/` | 约 23 个按领域划分的 WS 消息路由：chat、conversation、card、memory、reflection、insights、integration、library、mcp、provider、embedding、asr、tts、settings、onboarding、risk、sandbox、tools、usage、skill_install、commands（斜杠命令）、scheduler。 |
| `risk_bridge.py` / `sandbox_bridge.py` | 异步会合点：后端等待按 `call_id` 索引的确认/逃逸决策 future，前端的答复经对应 handler  resolve。 |
| `integration_engine.py` | 递归三阶段集成执行：运行用户定义的多模型集成图。 |
| `events.py` | 事件类型定义，与前端 `lib/ws-client.ts` 互为镜像。 |
| `title_generator.py` | 从首条用户消息生成简短会话标题。 |

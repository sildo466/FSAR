# server — WebSocket 服务与 GUI 聊天引擎

> 语言：中文 | [English](server.en.md) · 返回 [模块索引](README.md)

FastAPI 应用、唯一 `/ws` JSON 端点，以及驱动对话的 `ChatEngine`。

| 文件 | 说明 |
|---|---|
| `ws_server.py` | FastAPI 应用入口：首跑把模板复制为 `fsar.yaml`；创建 `RiskBridge`、`ChatEngine`、`WSAuthenticator`；托管 `frontend/dist`；暴露 health、飞书 webhook、微信扫码、头像上传下载、`/ws/token`、技能安装、`/ws/scheduler` 等路由。`start(host, port)` 为服务入口。 |
| `chat_engine.py` | 核心类 `ChatEngine`（复用 CLI 的 LLM/工具/记忆栈跑在 WS 上）；另含 `resolve_chat_model()`、供集成/社交复用的 `handle_user_message()`。 |
| `handlers/` | 约 27 个按领域划分的 WS 消息路由：chat、conversation、card、memory、reflection、insights、integration、library、mcp、provider、embedding、asr、tts、settings、onboarding、risk、sandbox、tools、usage、skill_install、commands（斜杠命令）、scheduler、group、lan、notifications、screening、skin。 |
| `risk_bridge.py` / `sandbox_bridge.py` | 异步会合点：后端等待按 `call_id` 索引的确认/逃逸决策 future，前端的答复经对应 handler  resolve。 |
| `integration_engine.py` | 递归三阶段集成执行：运行用户定义的多模型集成图。 |
| `events.py` | 事件类型定义，与前端 `lib/ws-client.ts` 互为镜像。 |
| `title_generator.py` | 从首条用户消息生成简短会话标题。 |
| `group_engine.py` | 群聊编排：自主竞选、连环轮次、取消。 |
| `room_phase.py` / `room_stages.py` | 项目房间：`room_phase.py` 只看计划板就决定房间下一步去哪；`room_stages.py` 给每个成员一份自己的 git worktree。 |
| `room_runner.py` / `room_wiring.py` | 房间的调度器，以及把一条计划项变成一次回合、把其 diff 变成一个分支的接缝。 |
| `room_app.py` / `room_routes.py` / `room_ingress.py` | 面向局域网的房间 API、它的路由，以及给"非本机用户"的成员用的环回入口。 |
| `promote_gate.py` | 允许什么离开暂存副本——检查文件权限位与可执行形状；不运行任何东西。 |
| `patch_text.py` / `patch_landing.py` | 写之前先读补丁，然后把它落到分支上。 |
| `plan_sink.py` / `publish_export.py` | `plan_write` 把清单写到哪，以及按白名单离开项目的快照。 |
| `agent_doc.py` | 每个房间成员在动手之前读到的那一份文本。 |
| `lan_supervisor.py` | 拥有第二个 uvicorn 监听——面向网络的那一个。 |
| `birthday_runner.py` | 生日决策之后的实际动作：解锁皮肤、写信。 |

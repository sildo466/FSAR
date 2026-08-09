# server — WebSocket server & GUI chat engine

> Language: [中文](server.md) | English · Back to [module index](README.en.md)

The FastAPI app, the single `/ws` JSON endpoint, and the `ChatEngine` that drives conversations.

| File | Description |
|---|---|
| `ws_server.py` | FastAPI entry: copies the template to `fsar.yaml` on first run; creates `RiskBridge`, `ChatEngine`, `WSAuthenticator`; serves `frontend/dist`; exposes routes for health, the Feishu webhook, WeChat QR login, avatar upload/download, `/ws/token`, skill install, and `/ws/scheduler`. `start(host, port)` is the server entry. |
| `chat_engine.py` | The core `ChatEngine` class (reuses the CLI LLM/tool/memory stack over WS); plus `resolve_chat_model()` and `handle_user_message()` (reused by integrations/social). |
| `handlers/` | ~23 domain-split WS routers: chat, conversation, card, memory, reflection, insights, integration, library, mcp, provider, embedding, asr, tts, settings, onboarding, risk, sandbox, tools, usage, skill_install, commands (slash commands), scheduler. |
| `risk_bridge.py` / `sandbox_bridge.py` | Async rendezvous: the backend awaits a confirm/escape decision future keyed by `call_id`; the frontend's answer resolves it via the matching handler. |
| `integration_engine.py` | Recursive three-phase integration execution of user-defined multi-model graphs. |
| `events.py` | Event type definitions; mirrors `frontend/src/lib/ws-client.ts`. |
| `title_generator.py` | Generates a short conversation title from the first user message. |

# server — WebSocket server & GUI chat engine

> Language: [中文](server.md) | English · Back to [module index](README.en.md)

The FastAPI app, the single `/ws` JSON endpoint, and the `ChatEngine` that drives conversations.

| File | Description |
|---|---|
| `ws_server.py` | FastAPI entry: copies the template to `fsar.yaml` on first run; creates `RiskBridge`, `ChatEngine`, `WSAuthenticator`; serves `frontend/dist`; exposes routes for health, the Feishu webhook, WeChat QR login, avatar upload/download, `/ws/token`, skill install, and `/ws/scheduler`. `start(host, port)` is the server entry. |
| `chat_engine.py` | The core `ChatEngine` class (reuses the CLI LLM/tool/memory stack over WS); plus `resolve_chat_model()` and `handle_user_message()` (reused by integrations/social). |
| `handlers/` | ~27 domain-split WS routers: chat, conversation, card, memory, reflection, insights, integration, library, mcp, provider, embedding, asr, tts, settings, onboarding, risk, sandbox, tools, usage, skill_install, commands (slash commands), scheduler, group, lan, notifications, screening, skin. |
| `risk_bridge.py` / `sandbox_bridge.py` | Async rendezvous: the backend awaits a confirm/escape decision future keyed by `call_id`; the frontend's answer resolves it via the matching handler. |
| `integration_engine.py` | Recursive three-phase integration execution of user-defined multi-model graphs. |
| `events.py` | Event type definitions; mirrors `frontend/src/lib/ws-client.ts`. |
| `title_generator.py` | Generates a short conversation title from the first user message. |
| `group_engine.py` | Group chat orchestration: autonomous speaker election, chained turns, cancellation. |
| `room_phase.py` / `room_stages.py` | Project rooms: `room_phase.py` decides where a room goes next from the board alone; `room_stages.py` gives each member its own git worktree. |
| `room_runner.py` / `room_wiring.py` | The room's scheduler, and the seam that turns one plan item into a turn and its diff into a branch. |
| `room_app.py` / `room_routes.py` / `room_ingress.py` | The LAN-facing room API, its routes, and the loopback ingress for members that are not the local user. |
| `promote_gate.py` | What may leave a staging copy — file modes and executable shapes are inspected; nothing is run. |
| `patch_text.py` / `patch_landing.py` | Reading a patch before writing it, then landing it on a branch. |
| `plan_sink.py` / `publish_export.py` | Where `plan_write` puts its list, and the allowlisted snapshot that leaves the project. |
| `agent_doc.py` | The single text every room member reads before it acts on anything. |
| `lan_supervisor.py` | Owns the second uvicorn listener — the one that faces the network. |
| `birthday_runner.py` | The effects behind the birthday decisions: unlock the skin, write the letter. |

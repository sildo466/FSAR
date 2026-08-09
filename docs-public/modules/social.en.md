# social — social-platform bridge

> Language: [中文](social.md) | English · Back to [module index](README.en.md)

Connects external chat platforms into the same `ChatEngine` used by the GUI.

| File | Description |
|---|---|
| `channels.py` | Adapter contract: `ChannelAdapter`, `ChannelEvent`, `ReplyTarget`. |
| `adapters/` | `telegram.py` / `feishu.py` / `wechat.py`. |
| `router.py` | Routes inbound events into FSAR (`handle_user_message` companion completion) and queues outbound replies; handles muting and session state. |
| `outbox.py` | Persistent outbound retry queue. |
| `state.py` | SQLite persistence for social sessions, platform↔conversation bindings, adapter cursors. |
| `manager.py` | `build_router_and_adapters()` / `start_social()` / `stop_social()` lifecycle. |

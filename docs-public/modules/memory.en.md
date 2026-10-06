# memory — the memory system

> Language: [中文](memory.md) | English · Back to [module index](README.en.md)

Layered memory (short-term / long-term / semantic / user model) plus reflection, recall, the experience layer, and character/user cards. Most stores live in `data/memory.db`; vectors in `data/chroma`. Recall is dated — items carry their age, so a character can say how long ago something happened — and every write to these stores is screened for prompt injection before it lands.

| File | Description |
|---|---|
| `short_term.py` / `long_term.py` | Current-conversation context window / SQLite-persisted long-term memories. |
| `session_store.py` | Per-conversation metadata and message persistence. |
| `semantic.py` | ChromaDB vector semantic memory. |
| `user_model.py` | Preferences, habits, profile. |
| `recall.py` | `MemoryRecall.recall_for_context()` — unified interface returning an LLM-friendly context block (semantic history + preferences + patterns + profile). |
| `reflection.py` | `IdleReflector` (idle consolidation) + `TaskReflector` (per-task) + `ReflectionStore`; intensities OFF/LOW/MEDIUM/HIGH. |
| `feedback.py` | RLHF-style message ratings (from the UI's `chat.rate`). |
| `decision_log.py` | Per-tool-call tracking for self-evolution, with contextvars task context. |
| `experience_store.py` | Experience layer: DB-first procedural knowledge in SQLite (`experiences` etc.); states ACTIVE/STALE/ARCHIVED. |
| `experience_embedding.py` | On-demand vector search over experiences and memory chunks. |
| `embedder.py` + `*_embed.py` | Selects an OpenAI / LM Studio / Ollama embedder per config. |
| `cards.py` | Character / user cards and `CardRepo`; loads `data/emotion_default.json` default emotion formulas. |
| `workspace.py` | Sandbox workspace persistence, conversation↔workspace bindings, sandbox audit events. |
| `integrations.py` | Persistence and graph validation (`CycleError` etc.) for recursive integrations. |
| `candidates.py` / `judge.py` / `pack.py` | The injection path: recall results become individually judgeable candidates, an optional endpoint scores each by relevance, and the survivors are packed atomically into one shared character budget. |
| `rooms.py` / `room_plan.py` | Group chat rooms — a room is an entity that owns exactly one session — and the room's plan board. |
| `patches.py` / `publishes.py` | Patches waiting to be looked at, and the record of what has left the project. |
| `agent_members.py` / `member_tokens.py` | External agents as room members, and the credentials for members that are not the local user. |
| `lan_blocklist.py` / `auth_audit.py` | Addresses that may not reach the LAN listener at all, and the append-only identity audit. |
| `idempotency.py` | Request de-duplication for the LAN POSTs. |

In a room, a message is attributed to the member who said it, and each character writes back to its own memory plus a room-level memory.

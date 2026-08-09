# Project Overview

> Language: [中文](overview.md) | English

**FSAR** (Fully Self-evolving AI Companion) is a **local-first** AI companion: conversations, memories, decisions, and tools all run on your own machine, stored in a SQLite database under `~/.fsar/`. Nothing is uploaded to any FSAR server. It belongs to the user, not to a vendor.

The name is the design contract: **F**aithful · **S**afe · **A**daptive · **R**eflective.

## The four pillars

- **Faithful** — FSAR is the character you configured (character card: name, personality, scenario, emotion state), talking to the user you described (user card). It does not drift into a "generic assistant".
- **Safe** — Every tool call passes through layered checks: a hardcoded hardline guard blocks destructive commands (`rm -rf /`, `shutdown`, `mkfs`) before anything else; a risk engine classifies each tool as SAFE/LOW/MEDIUM/HIGH/CRITICAL; a workspace gate contains file access; a subprocess env scrubber strips API keys and tokens before running skills. See [`SECURITY.md`](../SECURITY.md).
- **Adaptive** — Each tool call is logged. A strategy injector synthesises a `## Learned Strategies` block from the decision log and user model; an experience store persists procedural knowledge so an MCP server installed in one session is recalled in the next.
- **Reflective** — Three reflection modes (per-task, on-failure, idle-batch) re-read conversations and update the user model: explicit preferences ("uses VSCode"), inferred profile ("often codes in the evening"), and recurring patterns. The next session opens with that context already in the system prompt.

## What it can do

- Run shell commands (PowerShell on Windows, bash elsewhere) with a hardline guard
- Read, write, and search files within a scoped workspace
- Open apps and URLs via a sandboxed alias map
- Search and fetch the web via the free [Exa MCP](https://mcp.exa.ai) server (no API key required)
- Analyze images and PDFs locally
- Operate your computer (Computer Use / cua): screenshot, click, type, keypress — gated separately
- Persist new skills as SQLite experience rows (install once, recall many times)
- Talk through Telegram, Feishu (Lark), and WeChat

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12+, FastAPI + WebSocket |
| Frontend | Tauri 2 + React + TypeScript (Vite) |
| Storage | SQLite (`memory.db` etc.) + ChromaDB (semantic vectors) |
| Models | OpenAI / Anthropic / Google / DeepSeek / any OpenAI-compatible endpoint / Ollama / LM Studio |
| CLI entry | `main.py` (console script `fsar`) |

## Architecture at a glance

```
                 ┌───────────────────────────────────────────┐
                 │  Frontend (Tauri 2 / React)  frontend/dist  │
                 │  Chat / Cards / Memory / Reflection / ...   │
                 └───────────────┬───────────────────────────┘
                                 │ WebSocket (JSON) + HTTP  /ws
                 ┌───────────────▼───────────────────────────┐
                 │  src/server   FastAPI app + ChatEngine      │
                 │  handlers/ (~23 routers)   RiskBridge       │
                 └───────────────┬───────────────────────────┘
                                 │
        ┌───────────────┬────────┴────────┬────────────────┐
        ▼               ▼                 ▼                ▼
   src/core        src/memory        src/tools        src/social
   agent loop /    short / long /    tool registry +  Telegram / Feishu /
   prompts /       semantic / user   built-in tools   WeChat adapters
   injectors       model / reflect
        │               │                 │
        │        ┌──────┴─────────────────┴──────────┐
        │        ▼                                    ▼
        │   src/security  risk engine / perms /    src/sandbox  hardline /
        │                 confirm / audit                          workspace gate / sensitive
        │        │                                    │
        └────────┴──────────┬─────────────────────────┘
                            ▼
                    src/skills  skill review gate + subprocess execution
                    src/mcp     external MCP servers
                    src/providers  LLM / TTS / ASR adapters
                    src/utils   config / LLM cache / logging / migrations
```

## A message, end to end

Taking a chat message from the GUI as an example (details in `src/server/chat_engine.py`):

1. **Ingress** — The frontend sends a JSON message over `/ws`; `ws_server._dispatch` tries each handler in turn. `chat.send` lands in `handlers/chat.py`, which spawns a task calling `ChatEngine.handle_send`.
2. **Preparation** — Ensures the conversation and its workspace binding, resolves the character card, and emits `chat.thinking`. Then it branches: `/`-prefixed text → slash command; an "integration" model selection → a multi-model integration graph; `companion` mode → a one-shot companion turn; otherwise → the agent loop.
3. **Prompt assembly** — Loads the agent tier (`agent.tier`), builds the system prompt from `AGENT_SYSTEM_PROMPT` + the character/user persona + `## Learned Strategies` + `## Experiences`, hydrates short-term memory, and fits it to the model's context window.
4. **Agent loop** — Iterates up to `max_tool_turns` turns: compacts context as needed, calls the LLM through the two-tier cache, and — when the response contains tool calls — executes them (in parallel where allowed). Higher tiers add adversarial verification and micro-reflection, until the model produces a final answer with no tool calls.
5. **The security gauntlet per tool call** (run in order; any deny stops the action):
   - **MCP gate** — tools carrying a `server_name` must pass server review/verification;
   - **Sandbox gate** — `WorkspaceGate` validates paths/commands; leaving the workspace triggers a "sandbox escape" confirmation awaiting `deny / allow_once / allow_session / allow_always`;
   - **Risk gate** — `RiskEngine.evaluate` yields `proceed / confirm / deny`; on confirm it awaits the frontend's response (which may grant session trust, trust the whole MCP server, or permanently deny);
   - **Execution** — for `run_command`, network-egress and read-blacklist checks run first, and the working directory is pinned to the workspace root;
   - **Post-execution** — a small model reviews the result, secrets are redacted, `chat.tool_result` is emitted, and the decision is written to the audit log.
6. **Wrap-up** — Tool results are appended and the loop continues until the answer is final; the conclusion is saved and streamed (optionally triggering TTS); per-tier task reflection runs, the idle reflector is bumped, and a conversation title is generated lazily.

## Where the data lives

Everything about you lives under `~/.fsar/`:

```
~/.fsar/config/        yaml configuration
~/.fsar/data/
  memory.db            conversations, decisions, user model, experience
  chroma/              semantic embeddings
  llm_cache.db         L1/L2 response cache
  tts_cache.db         TTS audio cache
  scheduler.db         scheduled tasks
  logs/                rotating logs + audit.log
```

Delete `~/.fsar/` to reset FSAR completely.

## What to read next

- [Module reference](modules/README.en.md) — the responsibility and key files of every source module
- [Configuration guide](configuration.en.md) — `fsar.yaml` item by item
- [Build / Test / Develop](development.en.md)
- [`SECURITY.md`](../SECURITY.md) — the security model and vulnerability reporting
- [`CONTRIBUTING.md`](../CONTRIBUTING.md) — contributing

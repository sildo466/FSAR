# FSAR Architecture Design

> **FSAR** — Fully Self-evolving AI Companion
> A personal AI that operates your computer, learns your patterns, and grows with you.

---

## 1. Core Principles

| Principle | Meaning |
|---|---|
| **User Sovereignty** | All data stored locally, zero cloud dependency |
| **Deep Adaptation** | Continuously learns user preferences, habits, work patterns |
| **High Privilege, Careful** | System-level capabilities with risk assessment and trust model |
| **Self-Evolving** | Learns from every interaction, optimizes decision quality |
| **Long-term Companion** | Persistent memory, cross-session continuity |
| **Persona-Driven** | Character cards + user cards make the relationship feel real, not transactional |

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                  Tauri + React GUI                                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │ Onboard  │ │ Chat +   │ │ Memory   │ │ Library  │ │ Settings │ │
│  │ Wizard   │ │ History  │ │ Browser  │ │ + Skills │ │ & Perms  │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘ │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────────┐  │
│  │ Insights │ │ Usage    │ │ Cards    │ │ Intergration Studio  │  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────────────┘  │
└──────────────────────────────────┬──────────────────────────────────┘
                                   │ WebSocket
┌──────────────────────────────────▼──────────────────────────────────┐
│                          FSAR Core Engine                            │
│                                                                       │
│  ┌──────────────┐ ┌──────────────┐ ┌────────────────────────────┐  │
│  │ ChatEngine   │ │ Sandbox      │ │ Persona / Card Engine       │  │
│  │ (per-convo)  │ │ Workspace    │ │  character + user cards     │  │
│  └──────────────┘ └──────────────┘ └────────────────────────────┘  │
│                                                                       │
│  ┌──────────────┐ ┌──────────────┐ ┌────────────────────────────┐  │
│  │ Risk Engine  │ │ Self-        │ │ Intergration Orchestrator   │  │
│  │              │ │ Evolution    │ │  main agent + sub-agents    │  │
│  └──────────────┘ └──────────────┘ └────────────────────────────┘  │
│                                                                       │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                       Tool System                                │ │
│  │  builtin (bash, file, web, app) | MCP | Skills | Voice (TTS/ASR)│ │
│  └────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────┬──────────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────────┐
│                       Memory Layer                                    │
│  SQLite + ChromaDB + semantic recall + experience store               │
└─────────────────────────────────────────────────────────────────────┘
```

### High-Level Data Flow

```
User message
  → Sandbox check (workspace allowlist)
  → Persona injection (character card + user card + memory block)
  → LLM provider (selected via Intergration or single)
  → Tool calls (gated by Risk Engine + Sandbox)
  → Reflect → user_model / experiences
  → Persist conversation row
  → Stream deltas back via WS
  → (Optional) TTS stream to audio device
```

---

## 3. PL2 Roadmap (Current Focus)

PL1 (Agent foundation phase) is **complete**. The next phase — **PL2 Persona & Workspace** — focuses on making FSAR feel like a *person*, not a tool. PL2 is roughly 70% of total project scope; completion brings the project from MVP to a usable daily-driver.

### PL2 Feature Buckets

| Bucket | Features | Status |
|---|---|---|
| **Onboarding** | First-run wizard (provider config, character card, user card) | Planned |
| **Persona** | Character card + user card schema, persona engine, prompt assembly | Planned |
| **Built-in Providers** | Curated provider presets (OpenAI / Anthropic / DeepSeek / Ollama / LMStudio / Zhipu / Qwen) | Planned |
| **Skills v2** | Drag-install (paste MD / URL fetch), DB-backed catalog, version pinning | Planned |
| **Sandbox Workspace** | Per-conversation workspace allowlist, LLM restricted to user-approved paths | Planned |
| **TTS + ASR** | Pluggable voice providers (Edge / OpenAI / local), push-to-talk, streaming playback | Planned |
| **Thinking Toggle** | Per-provider + per-mode flag to disable thinking blocks (saves tokens + stops leak into titles) | Planned |
| **Intergration** | Multi-agent groups: main agent selects sub-agents, OR all-sub-agents debate; user-built & shareable | Planned |
| **Chat File Upload** | Attach files to message → extract → inject as context block | Deferred to PL3 |
| **Computer Use** | Last phase, deferred indefinitely | Deferred |

### Why Persona-First

A tool that talks to itself is noise. A persona that knows your name, your project, and your quirks is a *companion*. Character cards drive tone; user cards drive relevance; together they cut generic-LLM behavior by ~60% in informal tests. PL2 puts these at the *center* of the prompt, not as an afterthought.

---

## 4. Onboarding Wizard

### 4.1 First-Run Detection

```
FSAR launches → no providers configured in fsar.yaml
              → DB empty (no character_cards, no user_cards)
              → Frontend receives `onboarding.required = true` in WS snapshot
              → Renders OnboardingWizard as full-screen overlay
```

The wizard is a 3-step linear flow. Each step is skippable (mark for later), but at minimum step 1 (provider) is enforced — without a provider, nothing else works.

### 4.2 Step Layout

```
┌─────────────────────────────────────────────────────────────┐
│  Welcome to FSAR                                  [skip ▶] │
│                                                              │
│  Step 1 of 3 — Provider                                      │
│                                                              │
│  ○ Built-in presets: [OpenAI] [Anthropic] [DeepSeek] [...]  │
│                                                              │
│  ○ Custom (enter manually):                                  │
│    Base URL:   https://api.openai.com/v1                     │
│    API Key:    ●●●●●●●●●●●●●●●        [test connection]     │
│    Model ID:   gpt-4o-mini                                  │
│                                                              │
│  [◀ Back]                                       [Next ▶]    │
└─────────────────────────────────────────────────────────────┘
```

### 4.3 WS Protocol (New)

```jsonc
// server → client (in snapshot)
{ "onboarding": { "required": true, "completed_steps": ["provider"] } }

// client → server
{ "type": "onboarding.complete_step", "step": "provider" | "character_card" | "user_card" }
{ "type": "provider.create_builtin", "preset": "openai" | "anthropic" | "deepseek" | "ollama" | "lmstudio" | "zhipu" | "qwen" }
{ "type": "provider.test_connection", "base_url": "...", "api_key": "...", "model": "..." }

// server → client
{ "type": "provider.test_result", "ok": true, "models": ["gpt-4o-mini", "gpt-4o", ...], "error": null }
{ "type": "onboarding.completed" }  // fires when all 3 steps done
```

### 4.4 Persistence

Onboarding state stored in `fsar.yaml` under `onboarding:` section, plus `user_cards` and `character_cards` SQLite tables. Re-running wizard is allowed (delete entries → wizard reappears).

---

## 5. Persona Engine (Character Card + User Card)

### 5.1 Why Persona Cards

Standard LLM prompts treat the assistant as a generic helper. Persona cards (originally from SillyTavern / Risu / Agnai) ground the assistant in a specific character with:
- A name and avatar
- A description (who they are)
- A personality (how they behave)
- A scenario (where they are)
- Example dialogues (how they speak)

User cards do the same for the user — without them, the LLM doesn't know if you're a sysadmin, a writer, a student, or just curious.

### 5.2 Schema

```sql
CREATE TABLE IF NOT EXISTS character_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    avatar_path TEXT,                     -- local file path or data URL
    description TEXT NOT NULL,             -- 50-500 chars
    personality TEXT NOT NULL,             -- 20-200 chars
    scenario TEXT DEFAULT '',              -- 50-300 chars
    system_prompt_override TEXT DEFAULT '', -- if set, replaces AGENT_SYSTEM_PROMPT
    example_dialogues TEXT DEFAULT '[]',   -- JSON list of {user, assistant} pairs
    tags TEXT DEFAULT '[]',                -- searchable tags
    is_default INTEGER NOT NULL DEFAULT 0, -- only one card can be default
    created_by TEXT NOT NULL DEFAULT 'user',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    avatar_path TEXT,
    description TEXT NOT NULL,             -- user bio / role
    preferences TEXT DEFAULT '{}',          -- JSON key/value
    interests TEXT DEFAULT '[]',            -- JSON list
    communication_style TEXT DEFAULT '',     -- e.g. "concise, no emojis"
    is_default INTEGER NOT NULL DEFAULT 0,
    created_by TEXT NOT NULL DEFAULT 'user',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

### 5.3 Built-in Cards

Bundled `data/cards/` directory ships with 3 starter cards:
- **default-companion.json** — friendly, curious, no specific scenario
- **coding-coach.json** — patient teacher, scenario = "reviewing PR"
- **research-analyst.json** — formal, citation-heavy

User cards ship with one default: **default-user.json** ("{name}, prefers concise Chinese replies, working on a local-first AI project").

### 5.4 Prompt Assembly (New System Prompt Structure)

```
[CHARACTER CARD]
Name: <name>
Description: <description>
Personality: <personality>
Scenario: <scenario>

[EXAMPLE DIALOGUES]  (2-3 short pairs)
<user>: <msg>
<assistant>: <reply>
...

[USER CARD]
You are talking to <user_name>.
About them: <description>
Their style: <communication_style>
Known preferences: <preferences>
Known interests: <interests>

[SYSTEM BLOCKS — unchanged]
- AGENT_SYSTEM_PROMPT or system_prompt_override (if set)
- memory_block
- strategy_block
- experience_block
- MEMORY_POLICY
- skill_index (if any skills active)
```

### 5.5 Card Editor UI

Cards live at `/cards` page (new sidebar entry):
- List all character cards / user cards
- Click to edit (avatar upload, fields, example dialogues)
- "Set as default" toggle (enforces only-one-default via DB constraint)
- Import from JSON (paste SillyTavern V2 spec)
- Export to JSON (for sharing)

### 5.6 WS Protocol

```jsonc
{ "type": "card.list", "kind": "character" | "user" }
{ "type": "card.get", "kind": "...", "id": 1 }
{ "type": "card.upsert", "kind": "...", "card": { ... } }
{ "type": "card.delete", "kind": "...", "id": 1 }
{ "type": "card.set_default", "kind": "...", "id": 1 }
{ "type": "card.import_v2", "kind": "...", "json_text": "..." }   // SillyTavern V2 parser

// server → client
{ "type": "card.list_result", "kind": "...", "cards": [ ... ] }
{ "type": "card.imported", "kind": "...", "card": { ... } }
{ "type": "card.error", "kind": "...", "code": "...", "message": "..." }
```

---

## 6. Built-in Provider Presets

### 6.1 Why Presets

Users hit the most friction at "what URL do I paste?". Presets answer that question:

| Preset | base_url | default_model | notes |
|---|---|---|---|
| **OpenAI** | `https://api.openai.com/v1` | `gpt-4o-mini` | standard OpenAI compat |
| **Anthropic** | `https://api.anthropic.com` | `claude-haiku-4-5-20251001` | uses anthropic-specific headers |
| **DeepSeek** | `https://api.deepseek.com/v1` | `deepseek-chat` | OpenAI compat |
| **Zhipu GLM** | `https://open.bigmodel.cn/api/paas/v4` | `glm-4-flash` | OpenAI compat |
| **Qwen** | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-turbo` | OpenAI compat |
| **Ollama** | `http://127.0.0.1:11434/v1` | `qwen2.5:7b` | local, no key |
| **LMStudio** | `http://127.0.0.1:1234/v1` | (auto-discover via /v1/models) | local, no key |

### 6.2 Backend Schema

```python
BUILTIN_PRESETS = [
    {
        "id": "openai",
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
        "default_headers": {},
        "api_key_env": "OPENAI_API_KEY",
        "supports_thinking": False,
        "thinking_default": False,
    },
    {
        "id": "anthropic",
        "label": "Anthropic",
        "base_url": "https://api.anthropic.com",
        "default_model": "claude-haiku-4-5-20251001",
        "default_headers": {"anthropic-version": "2023-06-01"},
        "api_key_env": "ANTHROPIC_API_KEY",
        "supports_thinking": True,       # extended thinking
        "thinking_default": False,
    },
    # ...etc
]
```

### 6.3 Connection Test

`provider.test_connection`:
1. Sends `GET <base_url>/models` (OpenAI style) or provider-specific probe
2. Returns list of available models + `ok: true/false`
3. If 401/403 → `error: "auth_failed"`; if network error → `error: "unreachable"`

This lets the wizard show users "✓ Connected, 14 models available" before they commit.

---

## 7. Skills System v2

### 7.1 Current Pain

Skills are stored as `experiences` in SQLite (single body blob). Installation requires:
- Finding a SKILL.md on the web
- Manually copying the markdown
- Telling the LLM to install it (LLM uses file_ops → easy to fail)
- Repeating on every reinstall

This is friction. Skills should be installable as easily as browser extensions.

### 7.2 New Skill Schema

```sql
CREATE TABLE IF NOT EXISTS skills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,            -- slug, e.g. "ppt-maker-cli"
    version TEXT NOT NULL DEFAULT '1.0.0',
    description TEXT NOT NULL,
    category TEXT NOT NULL,                -- 'dev', 'office', 'data', 'media'
    body TEXT NOT NULL,                    -- SKILL.md main content (markdown)
    metadata_json TEXT NOT NULL DEFAULT '{}',  -- author, repo, license, triggers
    scripts_json TEXT NOT NULL DEFAULT '[]',   -- [{name, language, content}]
    references_json TEXT NOT NULL DEFAULT '[]', -- [{title, url, body}]
    source_url TEXT DEFAULT '',            -- original install source (if URL)
    install_method TEXT NOT NULL,          -- 'paste' | 'url' | 'bundle'
    state TEXT NOT NULL DEFAULT 'active',  -- active | stale | archived
    pinned INTEGER NOT NULL DEFAULT 0,
    use_count INTEGER NOT NULL DEFAULT 0,
    last_used_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

### 7.3 Two Install Paths

**A. Paste MD (offline):**
1. User opens `/library` → "Add Skill" → "Paste SKILL.md"
2. Pastes full markdown into a textarea
3. Frontend parses frontmatter (YAML between `---` markers) for `name`/`description`/`version`
4. `POST` to `/api/skill/import_paste` with `{body, metadata}`
5. Backend creates row immediately, no network, no LLM call

**B. URL fetch:**
1. User opens `/library` → "Add Skill" → "From URL"
2. Pastes a GitHub raw URL or gist URL
3. Backend fetches the markdown server-side (with size limit + SSRF check)
4. Same parsing flow, then `source_url` is recorded
5. For GitHub repos with `skills/<name>/SKILL.md` pattern, also fetch adjacent `scripts/` and `references/`

### 7.4 Skill Activation Model

Skills are NOT auto-loaded into every prompt (would explode token cost). Instead:
- `skill.index_block` — compact list of skill name + 1-line description (≤500 tokens)
- Injected only when user query matches a skill trigger (semantic match via skill metadata)
- LLM can call `skill_load(name)` to pull full body
- `use_count` + `last_used_at` updated on load → helps idle reflection surface rarely-used skills for cleanup

### 7.5 Skill Bundle Format

A skill directory on disk follows:
```
skills/
└── ppt-maker-cli/
    ├── SKILL.md              (required — main body)
    ├── metadata.yml          (required — name/version/description/triggers)
    ├── scripts/
    │   └── convert.py        (optional)
    └── references/
        └── api-notes.md      (optional)
```

`fsar skill import <path>` reads the directory, validates, inserts into DB.

---

## 8. Sandbox Workspace

### 8.1 Why

LLM-driven file ops currently write to *anywhere the process can write*. On a shared system or in production, this is a disaster. Even solo users get bitten — the LLM decides `/tmp` is fine, then `/etc/...` looks reasonable.

### 8.2 Design

```sql
CREATE TABLE IF NOT EXISTS workspaces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    root_path TEXT NOT NULL,           -- absolute path, e.g. "/home/u/projects/foo"
    allowed_paths TEXT NOT NULL,        -- JSON array of allowed sub-paths (relative to root)
    blocked_patterns TEXT DEFAULT '[]', -- JSON array of glob patterns always blocked
    default_for_new INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversation_workspaces (
    conversation_id TEXT PRIMARY KEY,  -- FK to sessions.id
    workspace_id INTEGER NOT NULL,      -- FK to workspaces.id
    granted_at TEXT NOT NULL
);
```

### 8.3 Enforcement Layers

1. **Tool gate (server-side, mandatory):** every file/bash tool that takes a path checks `path.is_relative_to(workspace_root)` and rejects otherwise.
2. **Risk Engine integration:** any tool call that escapes the workspace is auto-escalated to `CRITICAL` risk and requires explicit user approval.
3. **Per-conversation binding:** user picks workspace when creating a conversation; default workspace is used if not picked. Switching workspace mid-conversation requires confirmation.

### 8.4 WS Protocol

```jsonc
{ "type": "workspace.list" }
{ "type": "workspace.create", "name": "...", "root_path": "...", "allowed_paths": ["src", "tests"] }
{ "type": "workspace.set_default", "id": 1 }
{ "type": "workspace.bind", "conversation_id": "...", "workspace_id": 1 }
```

### 8.5 Tradeoffs Acknowledged

- Workspace is per-conversation, NOT per-task — simpler mental model
- User can grant escape approval per-call (bypass sandbox); audit-logged
- Default workspace is the user's home directory (read-only access for tools like `file_read`)

---

## 9. TTS + Voice Recognition (ASR)

### 9.1 Pluggable Voice Providers

Same factory pattern as LLM providers. Built-in presets:

| Preset | Engine | Notes |
|---|---|---|
| **edge-tts** | Microsoft Edge online TTS | Free, decent quality, requires internet |
| **openai-tts** | OpenAI TTS API | `tts-1`, `tts-1-hd`, 6 voices |
| **piper-local** | Local Piper | Offline, smaller model, fast on CPU |
| **elevenlabs** | ElevenLabs | High quality, paid |

ASR presets:

| Preset | Engine | Notes |
|---|---|---|
| **whisper-local** | faster-whisper | Offline, GPU-accelerated if available |
| **openai-asr** | OpenAI Whisper API | High accuracy, paid |
| **browser-asr** | Web Speech API | Free, browser-native, lower accuracy |

### 9.2 Schema

```sql
CREATE TABLE IF NOT EXISTS voice_providers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    preset_id TEXT NOT NULL,           -- 'edge-tts', 'openai-tts', etc.
    config_json TEXT NOT NULL DEFAULT '{}',
    enabled INTEGER NOT NULL DEFAULT 1,
    is_default_tts INTEGER NOT NULL DEFAULT 0,
    is_default_asr INTEGER NOT NULL DEFAULT 0
);
```

### 9.3 GUI

- Topbar mic icon → push-to-talk → streams audio to ASR → final transcript injected as user message
- Reply audio (TTS) toggle in Chat toolbar → when on, each assistant reply streams audio alongside text
- Voice settings page (`/settings/voice`): pick TTS preset, ASR preset, voice/speed/lang

### 9.4 WS Protocol

```jsonc
{ "type": "voice.asr.transcript", "text": "..." }       // final ASR result
{ "type": "voice.tts.request", "text": "...", "voice": "alloy" }
{ "type": "voice.tts.audio_chunk", "seq": 1, "audio": "<base64 mp3>" }
{ "type": "voice.tts.done", "seq": N }
```

Audio is base64-encoded MP3 chunks over WS. For long replies, client accumulates and plays in order.

---

## 10. LLM Thinking Toggle

### 10.1 The Problem

Thinking models (DeepSeek-R1, Claude with extended thinking, Qwen-QwQ, o1/o3) emit `<think>...</think>` blocks. These:
- Inflate token cost 2-10×
- Leak into titles, memory blocks, exports
- Don't always disable via API flag (provider-specific)

### 10.2 Design

```sql
ALTER TABLE llm_providers ADD COLUMN thinking_enabled INTEGER NOT NULL DEFAULT 1;  -- 0 = off
```

Per-provider toggle in Settings → Models. When `thinking_enabled = 0`:
1. Backend adds `?thinking=disabled` or similar provider-specific flag
2. Backend post-processes response: strip `<think>...</think>` blocks before streaming deltas
3. TitleGenerator already has `_strip_think` from PL1; we reuse that logic in `chat_engine._emit_text`

### 10.3 UI

Each provider row in `/settings/models` has a "Thinking" toggle. For providers that don't support thinking at all, toggle is disabled with tooltip "this provider doesn't support thinking".

### 10.4 Tradeoffs

- Some models can't truly disable thinking — the toggle is a *best-effort*. Strip-think is a safety net.
- For Anthropic extended thinking, you actually want it enabled for complex tasks. Default: off for short-chat, on for agent mode.

---

## 11. Intergration — Multi-Agent Groups

The headline feature of PL2. **Intergration** (a name, not a typo) is a *user-configurable multi-agent ensemble* that behaves like a single model from the user's perspective.

### 11.1 Concepts

```
┌─────────────────────────────────────────────────┐
│ Intergration: "Code Review Board"               │
│                                                  │
│  ┌─────────────────────────────────────────┐   │
│  │ Main Agent (router + synthesizer)       │   │
│  │  model: claude-haiku-4-5                │   │
│  │  role: decide who to consult,           │   │
│  │        merge final reply                │   │
│  └─────────────────────────────────────────┘   │
│         │            │            │            │
│         ▼            ▼            ▼            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │ Sub 1    │  │ Sub 2    │  │ Sub 3    │    │
│  │ "Securi- │  │ "Perfor- │  │ "Style"  │    │
│  │  ty"     │  │ "mance"  │  │          │    │
│  │  model:  │  │  model:  │  │  model:  │    │
│  │  deepseek│  │  qwen-coder│ │  haiku  │    │
│  └──────────┘  └──────────┘  └──────────┘    │
└─────────────────────────────────────────────────┘
```

- **Sub-agent:** name + role + model + persona prompt + temperature. Independent.
- **Main agent:** model + decision strategy (`pick` or `debate`) + synthesizer prompt.
- **Intergration =** collection of {main agent + sub-agents + strategy + UI metadata}.

### 11.2 Decision Strategy (User-Configurable)

| Strategy | Behavior |
|---|---|
| **`pick`** (default, low-cost) | Main agent reads user message, picks 0-3 most-relevant sub-agents, queries them, merges. Sub-agents not picked are skipped. |
| **`debate`** (high-quality) | All sub-agents are queried in parallel. Main agent sees all replies, picks best elements / mediates conflicts / synthesizes final answer. |

User picks per-Intergration. No mix-and-match per-call (keeps mental model simple).

### 11.3 From User's Perspective

User creates an Intergration in `/intergration` page → names it "Code Review Board" → adds 3 sub-agents → picks `pick` strategy → saves. Now in the Chat page, the model dropdown shows:
```
Default (claude-haiku-4-5)
Code Review Board [Intergration]
GPT-4o-mini
...
```

User picks "Code Review Board" → all subsequent messages route through the Intergration. From the user's view, it's just one model.

### 11.4 Schema

```sql
CREATE TABLE IF NOT EXISTS integrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT DEFAULT '',
    strategy TEXT NOT NULL DEFAULT 'pick',  -- 'pick' | 'debate'
    main_agent_json TEXT NOT NULL,          -- {model, prompt, temperature}
    sub_agents_json TEXT NOT NULL,          -- [{id, name, role, model, prompt, temperature}]
    is_default INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

### 11.5 Execution Flow (`pick` strategy)

```
User message arrives
  → Main agent gets: system_prompt + sub-agent roster + user message
  → Main agent returns JSON: {selected: [1, 3], reasoning: "..."}
  → Backend calls sub-agents 1 and 3 IN PARALLEL with their personas + user message
  → Sub-agent replies collected
  → Main agent gets: original user message + selected sub-agent replies
  → Main agent returns FINAL synthesized reply (streamed to user)
```

### 11.6 Execution Flow (`debate` strategy)

```
User message arrives
  → ALL sub-agents called IN PARALLEL with their personas + user message
  → Main agent gets: user message + ALL sub-agent replies
  → Main agent returns FINAL synthesized reply, possibly acknowledging disagreements
  → Streamed to user
```

### 11.7 Intergration Sub-page (`/intergration`)

A new sidebar entry. Layout:

```
┌─────────────────────────────────────────────┐
│ Intergrations                  [+ New]      │
├─────────────────────────────────────────────┤
│ Code Review Board          [edit] [delete]  │
│   strategy: pick                             │
│   main: claude-haiku-4-5                    │
│   subs: Security, Performance, Style         │
│                                              │
│ Research Team               [edit] [delete]  │
│   strategy: debate                           │
│   main: gpt-4o-mini                         │
│   subs: Historian, Scientist, Critic         │
└─────────────────────────────────────────────┘
```

Clicking edit opens an editor:
- Name, description
- Strategy (radio: pick / debate)
- Main agent config (model dropdown, persona textarea, temperature slider)
- Sub-agents list (drag to reorder, click to edit)
- Test panel (input box + "Run once" button → see how the Intergration responds)

### 11.8 Token Cost

Intergration is *expensive* by design. `pick` roughly 1.5-2× a normal call (router + selected subs). `debate` 3-5×. Surface this clearly in the editor with an estimated cost badge. Default is `pick` with max 2 sub-agents selected.

### 11.9 WS Protocol

```jsonc
{ "type": "integration.list" }
{ "type": "integration.create", "draft": { ... } }
{ "type": "integration.update", "id": 1, "patch": { ... } }
{ "type": "integration.delete", "id": 1 }
{ "type": "integration.run_once", "id": 1, "message": "..." }

// server → client
{ "type": "integration.list_result", "items": [ ... ] }
{ "type": "integration.run_started", "id": 1, "sub_calls": [1, 3] }
{ "type": "integration.sub_reply", "sub_id": 1, "delta": "..." }
{ "type": "integration.sub_done", "sub_id": 1 }
{ "type": "integration.main_delta", "delta": "..." }
{ "type": "integration.main_done" }
```

---

## 12. Memory + Self-Evolution (PL1 carryover, unchanged)

The self-evolution pipeline built in PL1 is the engine that makes PL2 *feel alive*:

```
Conversation
  → Per-task reflection (TaskReflector) → user_model + task_reflections
  → Idle reflection (IdleReflector, GUI-configured triggers) → user_model + auto-promoted experiences
  → Both feed into next prompt as memory_block + experience_block
```

This already runs (verified PL1). PL2 enhances it by:
- Character cards + user cards feed user_model automatically (when user sets a card, the LLM "knows" the user)
- Skills auto-load triggers get smarter (skill metadata indexed by user_model patterns)

---

## 13. Tool System (PL1 carryover, expanded)

### 13.1 Built-in Tools (already shipped)

| Tool | Risk | Notes |
|---|---|---|
| `run_command` | HIGH (sandboxed in PL2) | bash / powershell |
| `file_ops` | MEDIUM (sandboxed in PL2) | read/write/edit/list |
| `web_search` | LOW | DuckDuckGo / Brave API |
| `web_fetch` | LOW | URL → markdown |
| `app_control` | MEDIUM | open/close/focus apps |

### 13.2 PL2 Additions

| Tool | Purpose |
|---|---|
| `card_edit` | LLM-driven update of character/user cards (with confirmation) |
| `skill_load` | Pull full skill body into context |
| `integration_call` | Sub-agent invocation from main agent prompt |
| `workspace_status` | Show current workspace + allowed paths |

---

## 14. Risk Assessment (PL2-augmented)

| Level | Description | Action |
|---|---|---|
| `SAFE` | Read file (within workspace), search, query | Execute silently |
| `LOW` | Write new file (within workspace), create dir | Execute + log |
| `MEDIUM` | Modify/delete file (within workspace), run command (within workspace) | Notify user |
| `HIGH` | Escape workspace, system ops, registry, network external | Wait for confirmation |
| `CRITICAL` | Batch delete, permission changes, sandbox escape attempt | Warn + double confirm + log to audit |

Sandbox adds two new auto-escalation rules:
- Any tool call whose resolved path is OUTSIDE the active workspace → `HIGH` minimum, `CRITICAL` if file is outside user home
- Bash command containing `rm -rf`, `del /f /s`, `format`, etc. → `CRITICAL` regardless of workspace

---

## 15. Project Structure

```
FSAR/
├── docs/
│   ├── DESIGN.MD              # This document
│   └── superpowers/specs/      # Phase-specific designs
│
├── src/
│   ├── core/
│   │   ├── prompts.py          # System prompt assembly (now persona-aware)
│   │   ├── persona.py          # NEW: card → prompt block
│   │   ├── voice.py            # NEW: TTS/ASR provider factory
│   │   └── integration.py      # NEW: multi-agent orchestrator
│   │
│   ├── memory/
│   │   ├── ...                  # PL1 memory stack
│   │   ├── cards.py             # NEW: character/user card CRUD
│   │   ├── skills.py            # NEW: skill catalog + import
│   │   └── workspaces.py        # NEW: workspace + binding
│   │
│   ├── server/
│   │   ├── chat_engine.py       # sandbox-aware, persona-aware
│   │   ├── onboarding.py        # NEW: wizard orchestration
│   │   └── handlers/
│   │       ├── card.py          # NEW
│   │       ├── skill.py         # NEW
│   │       ├── workspace.py     # NEW
│   │       ├── voice.py         # NEW
│   │       └── integration.py   # NEW
│   │
│   ├── tools/
│   │   ├── builtin/             # bash, file_ops, web_*
│   │   └── sandbox.py           # NEW: path validation gate
│   │
│   └── providers/
│       ├── llm/                 # factory + presets
│       ├── tts/                 # NEW: voice factory
│       └── asr/                 # NEW: ASR factory
│
├── data/
│   ├── cards/                   # NEW: built-in character/user cards
│   └── skills/                  # NEW: local skill bundles
│
├── frontend/src/
│   ├── pages/
│   │   ├── Onboarding.tsx       # NEW
│   │   ├── Cards.tsx            # NEW
│   │   ├── Intergration.tsx     # NEW
│   │   ├── Voice.tsx            # NEW
│   │   └── ...
│   ├── components/
│   │   ├── voice/               # NEW
│   │   ├── card/                # NEW
│   │   └── integration/         # NEW
│   └── stores/
│       ├── onboarding.ts        # NEW
│       ├── voice.ts             # NEW
│       └── integration.ts       # NEW
│
└── tests/
    ├── test_persona.py          # NEW
    ├── test_sandbox.py          # NEW
    ├── test_integration.py      # NEW
    └── ...
```

---

## 16. PL2 Development Sub-Phases

PL2 itself is too large for one push. Sub-phases in priority order:

### 16.1 PL2.0 — Persona Foundation (most critical, ~2 weeks)

- Character card schema + CRUD
- User card schema + CRUD
- 3 built-in character cards, 1 built-in user card
- Persona injection into system prompt
- `/cards` page
- WS protocol for cards
- Tests: persona assembly, card CRUD

**Exit criteria:** user can create a character, switch to it, see the persona take effect in next reply.

### 16.2 PL2.1 — Onboarding Wizard (✅ 2026-07-10, ~3 days)

- First-run detection (auto-creates `config/fsar.yaml` from template on clean install)
- 3-step wizard (provider → user card → character card)
- 25 built-in LLM provider presets (no hardcoded models per B-D1; user selects or types)
- `provider.test_connection` with 5s timeout + error classification (ok / auth_failed / unreachable / model_required / bad_request / deferred / unknown)
- `provider.fetch_models` for vendors exposing `/models` endpoint
- Anthropic test uses user-typed model (no hardcoded test models)
- Google Gemini preset is `deferred: true` (UI greys it out; protocol ships in PL2.5)
- SillyTavern V2 PNG import via PNG tEXt chunk parser
- Skip / resume support; per-step atomic fsar.yaml writes via FsarConfig
- Settings → Advanced has [Reset Onboarding] button
- Tests: 32 backend (pytest) + 96 frontend (vitest) passing

**Exit criteria (met):** clean install → wizard appears → finishes → /chat with configured LLM.

### 16.3 PL2.2 — Sandbox Workspace (~1.5 weeks)

- Workspace CRUD + binding
- Tool-level path validation gate
- Risk Engine integration (auto-escalate escape)
- Default workspace = user home
- WS protocol for workspace
- `/settings/workspace` page
- Tests: path allowlist, escape detection, escalation

**Exit criteria:** LLM attempting `/etc/passwd` access is blocked + escalated.

### 16.4 PL2.3 — Skills v2 (~1 week)

- Skill schema (separate from experiences)
- Import via paste + URL fetch
- Skill index block in prompt (lazy load)
- `/library` updated UI
- Tests: import, parse, activate

### 16.5 PL2.4 — Thinking Toggle (~0.5 week)

- Per-provider `thinking_enabled` column
- Strip-think in chat_engine
- Settings UI toggle

### 16.6 PL2.5 — TTS + ASR (~2 weeks)

- Voice provider factory
- Edge-TTS + OpenAI-TTS + Piper presets
- Whisper-local + OpenAI-ASR presets
- Topbar mic push-to-talk
- Reply audio stream
- `/settings/voice` page

### 16.7 PL2.6 — Intergration (the headline, ~3 weeks)

- Integration schema
- Main agent + sub-agents config
- `pick` strategy
- `/intergration` page + editor
- `debate` strategy
- Test panel
- WS protocol
- Cost estimation

### 16.8 PL2.7 — Polish & Cross-Cutting (~1 week)

- Onboarding completion animation
- Audit log UI (security review)
- Voice in Intergration (sub-agent can speak?)
- Documentation site
- Migration: existing users get a "complete onboarding" banner (not blocking)

**PL2 total: ~10 weeks of focused work.**

---

## 17. PL3+ (post-PL2, optional)

- Tauri desktop packaging (signing, auto-update)
- Mobile companion app (read-only mirror)
- Cloud sync (opt-in, E2E encrypted)
- Voice call mode (continuous mic, no push-to-talk)
- Plugin marketplace
- Computer Use polish (if ever revisited)

---

## 18. Technical Decisions Log

| Decision | Rationale | Date |
|---|---|---|
| Persona cards as SQLite tables (not JSON files) | Queryable, version-controllable, joins with memories | PL2 |
| Built-in cards in `data/cards/` not hardcoded | User can edit defaults; first-run detects edits | PL2 |
| Intergration = SQLite (not file) | Same as skills; shareable via export | PL2 |
| Sandbox = per-conversation (not per-task) | Simpler mental model; users think in conversations | PL2 |
| Thinking toggle = best-effort (provider flag + strip) | Some providers can't truly disable; safety net required | PL2 |
| TTS over WS (not local file) | Live streaming aligned with chat delta | PL2 |
| Skills activation = lazy (semantic match) | Avoids token explosion | PL2 |
| Integration strategy = user-pick (no auto-mix) | Predictable cost; users learn what they're paying for | PL2 |
| Workspace allowlist = relative paths | User grants "src/", "tests/", not "C:\Users\u\proj\src\" — portable | PL2 |
| Voice providers = same factory pattern as LLM | Consistency; user reuses provider concepts | PL2 |

---

## 19. Open Questions for PL2

| # | Question | Owner | Blocker? |
|---|---|---|---|
| Q1 | Should user cards auto-fill from conversation history (LLM-inferred)? | TBD | No |
| Q2 | Should Intergration results be cacheable? (likely yes, same as LLM cache) | TBD | Yes for cost |
| Q3 | Can sub-agents themselves be Intergrations? (recursion limit: 2 levels) | TBD | No |
| Q4 | When workspace is unset, is the LLM read-only-by-default? | TBD | UX question |
| Q5 | TTS audio in Intergration — one voice per sub or one voice for synthesis? | TBD | No |
| Q6 | Should we ship a marketplace for community Intergrations? | TBD | Future |

---

## 20. Closing

PL1 built the engine. PL2 gives it a face, a voice, a workspace, and a team. By PL2 completion, FSAR is no longer a "tool you operate" — it's an entity you collaborate with.

Computer Use stays deferred. The remaining 30% (Tauri packaging, sync, marketplace, CU polish) is "how it ships" rather than "what it is". PL2 is the soul.
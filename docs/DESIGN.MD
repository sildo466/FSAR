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

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Tauri + React GUI                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────┐ │
│  │ Chat     │  │ Task     │  │ Memory   │  │ Settings   │ │
│  │ Panel    │  │ Board    │  │ Browser  │  │ & Perms    │ │
│  └──────────┘  └──────────┘  └──────────┘  └────────────┘ │
└──────────────────────────┬──────────────────────────────────┘
                           │ WebSocket
┌──────────────────────────▼──────────────────────────────────┐
│                      FSAR Core Engine                         │
│                                                               │
│  ┌────────────┐  ┌────────────┐  ┌────────────────────────┐ │
│  │ Risk       │  │ Self-      │  │ User Model             │ │
│  │ Engine     │  │ Evolution  │  │ Preferences / Habits   │ │
│  └────────────┘  └────────────┘  └────────────────────────┘ │
│                                                               │
│  ┌────────────────────────────────────────────────────────┐ │
│  │                    Tool System                          │ │
│  │                                                         │ │
│  │  Phase 1: Foundation Tools (reliable, deterministic)    │ │
│  │  ┌─────────┐  ┌──────────┐  ┌──────────┐              │ │
│  │  │ bash/   │  │ file_    │  │ web_     │              │ │
│  │  │ powershell│ │ ops      │  │ search   │              │ │
│  │  └─────────┘  └──────────┘  └──────────┘              │ │
│  │                                                         │ │
│  │  Phase 2: Integration Tools                             │ │
│  │  ┌─────────┐  ┌──────────┐  ┌──────────┐              │ │
│  │  │ MCP     │  │ Skills   │  │ App      │              │ │
│  │  │ Client  │  │ Engine   │  │ Control  │              │ │
│  │  └─────────┘  └──────────┘  └──────────┘              │ │
│  │                                                         │ │
│  │  Phase 3: Computer Use (GUI automation, least reliable)│ │
│  │  ┌──────────────────────────────────────────────────┐  │ │
│  │  │  Screenshot → UIA Tree → LLM Decision → Click/  │  │ │
│  │  │  Type/Scroll → Verify → Loop                      │  │ │
│  │  └──────────────────────────────────────────────────┘  │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                               │
│  ┌────────────────────────────────────────────────────────┐ │
│  │                    Memory System                        │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐ │ │
│  │  │ SQLite   │  │ ChromaDB │  │ User Model DB        │ │ │
│  │  │ Episodic │  │ Semantic │  │ Preferences / Trust  │ │ │
│  │  └──────────┘  └──────────┘  └──────────────────────┘ │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

### Tool Call Priority

> **Key insight:** FSAR built Computer Use first, but discovered that most tasks are better solved with deterministic tools. GUI automation is the least reliable option and should be the last resort.

| Priority | Tool Type | Reliability | Use When |
|---|---|---|---|
| 1 | `bash` / `powershell` | High | System commands, file operations, URL schemes |
| 2 | `file_read` / `file_write` | High | Reading/writing local files |
| 3 | `web_search` / `web_fetch` | High | Information retrieval |
| 4 | `app_control` (URL schemes, shortcuts) | High | Opening apps, deep linking |
| 5 | `computer_use` (GUI automation) | **Low** | Only when ALL above tools cannot accomplish the task |

**Example:** "给微信的 sunny qi 发消息" → `start wechat://` opens WeChat (priority 4). Only use GUI automation if the specific action (typing in a specific chat) can't be done via URL scheme.

### Lessons Learned from Computer Use

1. **Per-window > full-desktop** — CUA captures the target window at native resolution, not the full screen. This makes coordinates much more accurate for the LLM.
2. **Grid overlay must be on original resolution** — Drawing the grid on a resized image makes coordinates wrong. Grid → resize → send to LLM.
3. **LLM coordinates need window-origin offset** — LLM outputs window-relative coordinates. Program converts: `screen = window_origin + (coord × ratio)`.
4. **SendInput > PostMessage** — PostMessage is silently dropped by Chromium/Electron/Qt apps. SendInput (system-level injection) works universally.
5. **UIA tree is unreliable for custom-rendered apps** — WeChat, browsers, games render their own UI. UIA tree is empty. Coordinate clicks are the only option.
6. **Window tracking is fragile** — Qt apps recreate windows on state transitions (login → main). Need robust re-finding by PID.
7. **Function calling > JSON parsing** — OpenAI tools API eliminates regex parsing errors. Model output is always structured.
8. **LLM coordinate estimation is imprecise** — Even with grid overlay, LLMs (especially smaller ones) can't read exact pixel coordinates. Use when no alternative exists.

---

## 3. Computer Use Engine (Current Implementation)

> Self-built, no external dependency. Located at `src/computer_use/`.

### 3.1 Architecture

```
┌──────────────────────────────────────────────────────────┐
│                   FSAR Orchestrator                        │
│               (src/orchestrator/)                          │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐ │
│  │  Agent Loop                                           │ │
│  │  1. get_window_state(pid, hwnd) → screenshot + tree   │ │
│  │  2. Build LLM message (system prompt + grid screenshot│ │
│  │     + element tree + action history)                   │ │
│  │  3. LLM function call → tool_call(name, args)         │ │
│  │  4. Execute action via input_actions                   │ │
│  │  5. Verify result → record to history                  │ │
│  │  6. Loop until done or max steps                       │ │
│  └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
┌─────────────┐  ┌──────────────────┐  ┌──────────────────┐
│  snapshot   │  │  input_actions   │  │  window_manager  │
│  UIA tree   │  │  click / type /  │  │  list / launch / │
│  + screenshot│  │  key / scroll    │  │  find / kill     │
└─────────────┘  └──────────────────┘  └──────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
┌─────────────┐  ┌──────────────────┐  ┌──────────────────┐
│ screen_     │  │  Windows API     │  │  Windows API     │
│ capture     │  │  PostMessage     │  │  EnumWindows     │
│ PrintWindow │  │  SendInput       │  │  ShellExecute    │
│ BitBlt      │  │  UIA patterns    │  │  AppsFolder      │
│ DWM crop    │  │                  │  │                  │
└─────────────┘  └──────────────────┘  └──────────────────┘
```

### 3.2 Key Modules

| Module | File | Responsibility |
|---|---|---|
| **Orchestrator** | `src/orchestrator/fsar_orchestrator.py` | Agent loop, LLM interaction, function calling, history |
| **Snapshot** | `src/computer_use/snapshot.py` | UIA tree walk, element indexing, markdown rendering |
| **Screen Capture** | `src/computer_use/screen_capture.py` | PrintWindow, BitBlt, DWM crop, grid overlay |
| **Input Actions** | `src/computer_use/input_actions.py` | Click, type, key, scroll with SendInput/PostMessage/UIA |
| **Window Manager** | `src/computer_use/window_manager.py` | Window enumeration, app launch, window finding |

### 3.3 Screenshot Pipeline

```
capture_window(hwnd)
  ├─ PrintWindow(PW_RENDERFULLCONTENT)     ← works for occluded GDI windows
  ├─ if black → BitBlt from screen DC      ← works for visible windows
  └─ if still black → SetForegroundWindow  ← for Chromium/DirectComposition
     + BitBlt again
     + restore previous foreground

add_grid_overlay(png, step=50)
  └─ Draw semi-transparent grid lines with coordinate labels
     LLM reads coordinates directly from the grid

resize_if_needed(png, max_dim=1568)
  └─ Downscale if needed, return (png, ratio) for coordinate scaling
```

### 3.4 Click Dispatch Strategy

```
click_element(hwnd, element_index=..., x=..., y=...)
  │
  ├─ By element_index:
  │   ├─ Try UIA patterns (Invoke → Toggle → Select → Expand)
  │   │   with 5-second timeout per pattern
  │   ├─ If all fail → get element's BoundingRectangle center
  │   └─ Fall through to coordinate click
  │
  └─ By coordinates (x, y):
      ├─ Convert window-relative → screen coordinates
      │   (screen_x = window_rect.left + x, screen_y = window_rect.top + y)
      │
      ├─ Detect target window class:
      │   ├─ Chrome_WidgetWin_* → SendInput (Chromium/Electron)
      │   ├─ Qt* / *QWindow*   → SendInput (Qt apps)
      │   ├─ HwndWrapper[*]    → SendInput (WPF)
      │   ├─ gdkWindow*        → SendInput (GTK)
      │   └─ Other             → PostMessage
      │
      ├─ SendInput path:
      │   ├─ Save previous foreground + cursor position
      │   ├─ SetForegroundWindow(target)
      │   ├─ SetCursorPos(screen_x, screen_y)
      │   ├─ SendInput(MOUSEEVENTF_LEFTDOWN/UP)
      │   └─ Restore previous foreground + cursor
      │
      └─ PostMessage path:
          ├─ ScreenToClient → client coordinates
          └─ PostMessage(WM_LBUTTONDOWN/UP)
```

### 3.5 Function Calling Architecture

The orchestrator uses **OpenAI function calling** (not free-form JSON parsing).

```python
# Tool definitions (TOOLS constant)
TOOLS = [
    {"type": "function", "function": {
        "name": "click",
        "parameters": {
            "properties": {
                "x": {"type": "integer"},      # Grid coordinate
                "y": {"type": "integer"},      # Grid coordinate
                "element_index": {"type": "integer"},  # Optional
            }
        }
    }},
    {"type": "function", "function": {"name": "type_text", ...}},
    {"type": "function", "function": {"name": "press_key", ...}},
    {"type": "function", "function": {"name": "hotkey", ...}},
    {"type": "function", "function": {"name": "launch_app", ...}},
    {"type": "function", "function": {"name": "scroll", ...}},
    {"type": "function", "function": {"name": "think", ...}},
    {"type": "function", "function": {"name": "done", ...}},
]

# LLM call
resp = llm.chat.completions.create(
    model="mimo-v2.5",
    messages=messages,
    tools=TOOLS,
    tool_choice="auto",
    max_tokens=4096,
    temperature=0.1,
)

# Extract structured tool call (no parsing needed)
tool_call = resp.choices[0].message.tool_calls[0]
action_name = tool_call.function.name
action_args = json.loads(tool_call.function.arguments)
```

**Why function calling > JSON parsing:**
- Parameter types enforced by schema (no `x: [148, 305]` list errors)
- No regex parsing needed (no `_parse_action` with 3 fallback strategies)
- Model output is always valid and structured

### 3.6 System Prompt (English)

The system prompt teaches the LLM how to read the grid overlay:

```
Coordinate System:
- Gray grid lines on the screenshot
- Numbers along TOP edge = X coordinates
- Numbers along LEFT edge = Y coordinates
- Origin (0,0) at top-left
- Read coordinates: find target → look UP for X → look LEFT for Y

Rules:
1. Screenshot is the ONLY source of truth
2. Click center of targets, not edges
3. Some apps render custom UI (not in element list) → use coordinates
4. After each action, observe next screenshot for verification
5. If same action fails 2x, MUST change strategy
```

### 3.7 Action History (In-Task Context)

The LLM receives the **complete action history** for the current task:

```json
[
  {"step": 1, "action": "launch_app", "params": {"name": "微信"}, "result": "success", "switched_to": "微信 (pid=39404)"},
  {"step": 2, "action": "click", "params": {"x": 148, "y": 320}, "result": "success"},
  {"step": 3, "action": "click", "params": {"x": 148, "y": 290}, "error": "timeout"},
  {"step": 4, "action": "type_text", "params": {"text": "在吗"}, "result": "success"}
]
```

Every entry has either `result: "success"` or `error: "具体报错"`, enabling the LLM to reflect on failures and adjust strategy.

---

## 4. Memory System

### 4.1 Memory Layers

```
┌─────────────────────────────────────────────────┐
│              Long-Term Memory                    │
│  ┌─────────────┐  ┌───────────────────────────┐ │
│  │ Episodic    │  │ Semantic                  │ │
│  │ (SQLite)    │  │ (ChromaDB vectors)        │ │
│  │ Events,     │  │ "User prefers dark mode"  │ │
│  │ tasks,      │  │ "User works on FSAR      │ │
│  │ outcomes    │  │  project in evenings"     │ │
│  └─────────────┘  └───────────────────────────┘ │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│              User Model                          │
│  ┌─────────────┐  ┌───────────────────────────┐ │
│  │ Preferences │  │ Behavioral Patterns       │ │
│  │ Editor,     │  │ "Usually checks email     │ │
│  │ terminal,   │  │  at 9am, codes in PM"     │ │
│  │ browser     │  │                           │ │
│  └─────────────┘  └───────────────────────────┘ │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│              Short-Term Memory                   │
│  Current session conversation context            │
│  (deque, max 50 messages)                        │
└─────────────────────────────────────────────────┘
```

### 4.2 Storage

| Type | Storage | Query |
|---|---|---|
| Episodic | SQLite | Time-based, keyword search |
| Semantic | ChromaDB | Vector similarity |
| User Model | SQLite + JSON | Direct lookup |
| Short-Term | In-memory deque | Last N messages |

---

## 5. Tool System (Planned)

> **Phase 1.5** — Foundation tools that should have come before computer use.

### 5.1 Tool Registry

```python
class ToolRegistry:
    def register(self, tool: Tool): ...
    def get_tools_for_llm(self) -> List[dict]: ...  # OpenAI function format
    def get(self, name: str) -> Tool: ...
```

### 5.2 Foundation Tools (Priority)

| Tool | Function | Risk | Reliability |
|---|---|---|---|
| `run_command` | Execute shell command | HIGH | High |
| `read_file` | Read file contents | SAFE | High |
| `write_file` | Write/create file | LOW | High |
| `list_dir` | List directory | SAFE | High |
| `move_file` | Move/rename | MEDIUM | High |
| `delete_file` | Delete file | HIGH | High |
| `web_search` | Search engine query | SAFE | High |
| `web_fetch` | Fetch webpage content | SAFE | High |
| `open_app` | Launch application | LOW | High |
| `screenshot` | Capture screen | SAFE | High |

### 5.3 Tool Execution Flow

```
User request → LLM selects tool (function calling)
  → ToolRegistry lookup
  → RiskEngine evaluation
    ├─ SAFE/LOW → execute silently
    ├─ MEDIUM → notify user, then execute
    └─ HIGH → wait for confirmation
  → tool.execute(args) → result → return to LLM
```

---

## 6. MCP Support (Implemented)

> **Phase 3.5 → Phase 4** — Connect to external tool servers.

```
┌──────────────────────────┐
│          FSAR             │
│  ┌────────────────────┐  │
│  │     MCP Client     │  │
│  └─────────┬──────────┘  │
└────────────┼─────────────┘
             │
    ┌────────┼────────┐
    ▼        ▼        ▼
┌───────┐ ┌───────┐ ┌───────┐
│ files │ │  db   │ │github │
│server │ │server │ │server │
└───────┘ └───────┘ └───────┘
```

MCP tools auto-register into ToolRegistry, unified with local tools.

---

## 7. Experience Layer (Phase 6)

> **DB-first knowledge accumulation** — procedural knowledge ("how you do X") + freeform memory ("what you told me"), all stored as SQLite rows. Reaches Hermes-style skill-library depth without the filesystem+sidecar complexity.

### 7.1 Design Rationale

Hermes-agent uses `SKILL.md` files + `references/` / `templates/` / `scripts/` subdirectories + `.usage.json` sidecar. FSAR instead models the same knowledge as relational rows:

| Hermes (filesystem) | FSAR p6 (SQLite) |
|---|---|
| `SKILL.md` body | `experiences.body` |
| `templates/<name>` | `experience_templates` table |
| `scripts/<name>` | `experience_scripts` table |
| `references/<name>` | `experience_references` table |
| `related_skills:` frontmatter | `experience_links` table |
| `.usage.json` sidecar | `experiences.use_count` + `last_used_at` columns |
| `.archive/` directory | `experiences.state = 'archived'` |
| `MEMORY.md` chunks | `memory_chunks` table |
| Background fork AIAgent → `skill_manage` | Sync `ExperienceStore` API + `/learn` command |

**Why DB-first wins here:**

- **ACID consistency** — body + templates + scripts all atomic, no sidecar sync issues
- **Queryable** — `WHERE category=? AND body LIKE ?` vs `grep -r` over directories
- **Vector-native** — ChromaDB embedding column on `experiences` and `memory_chunks`
- **Single file portability** — rsync `data/memory.db`, not 100+ directories
- **Lifecycle as SQL state machine** — `UPDATE experiences SET state='archived' WHERE last_used_at < ?`, no `mv` to `.archive/`
- **No LLM fork** — sync operations only, driven by `TaskReflector` output + user `/learn`
- **Same physical layer as p5** — extends existing `data/memory.db`, no new infrastructure

### 7.2 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   System Prompt (every turn)                 │
│                                                              │
│   ## Experiences (index — call experience_view to load body) │
│     file-management:                                         │
│       - download-organizer: Auto-classify by type and date.  │
│       - workspace-cleanup: Weekly stale-directory archive.   │
│     coding:                                                  │
│       - pr-review-checklist: Personal PR review standards.   │
│     research:                                                │
│       - paper-reading-workflow: Read → tag → cite pipeline.  │
│                                                              │
│   ## Memory (relevant chunks — top-3 by recall)              │
│     - User prefers Chinese in chat, English in code comments │
│     - 2024-03: User mentioned project A uses Postgres 14     │
└─────────────────────────────────────────────────────────────┘
                              ↓ LLM judges relevance
┌─────────────────────────────────────────────────────────────┐
│              experience_view(name) tool call                 │
│                                                              │
│   Returns: body + templates + scripts + references           │
│   Added as tool message in current turn → LLM context       │
│   Token cost only when actually used                         │
└─────────────────────────────────────────────────────────────┘
                              ↓
                       LLM follows procedure
```

### 7.3 Schema

```sql
-- Main procedural knowledge table (replaces SKILL.md)
CREATE TABLE experiences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    category TEXT NOT NULL,                 -- "file-management" / "coding" / "research"
    description TEXT NOT NULL,              -- ≤60 chars, system-prompt index entry
    body TEXT NOT NULL,                     -- full procedure / how-to
    trigger_patterns TEXT NOT NULL DEFAULT '[]',  -- JSON array of trigger phrases
    pitfalls TEXT NOT NULL DEFAULT '[]',    -- JSON array of known gotchas
    prerequisites TEXT NOT NULL DEFAULT '[]', -- JSON array of env / setup needs
    use_count INTEGER NOT NULL DEFAULT 0,
    last_used_at TEXT,
    state TEXT NOT NULL DEFAULT 'active',   -- active | stale | archived
    pinned INTEGER NOT NULL DEFAULT 0,
    created_by TEXT NOT NULL,               -- 'agent' | 'user' | 'task_reflection'
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX idx_experiences_category ON experiences(category);
CREATE INDEX idx_experiences_state ON experiences(state);
CREATE INDEX idx_experiences_last_used ON experiences(last_used_at);

-- Templates (replaces templates/<name>)
CREATE TABLE experience_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experience_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    content TEXT NOT NULL,
    FOREIGN KEY (experience_id) REFERENCES experiences(id) ON DELETE CASCADE
);

-- Scripts (replaces scripts/<name>)
CREATE TABLE experience_scripts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experience_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    language TEXT NOT NULL,                 -- "python" | "bash" | "powershell"
    content TEXT NOT NULL,
    FOREIGN KEY (experience_id) REFERENCES experiences(id) ON DELETE CASCADE
);

-- References / knowledge chunks (replaces references/<name>)
CREATE TABLE experience_references (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experience_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    source TEXT,                            -- "url" | "paste" | "conversation"
    source_url TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (experience_id) REFERENCES experiences(id) ON DELETE CASCADE
);

-- Relationship graph (replaces related_skills frontmatter)
CREATE TABLE experience_links (
    src_id INTEGER NOT NULL,
    dst_id INTEGER NOT NULL,
    relation TEXT NOT NULL,                 -- "extends" | "supersedes" | "related"
    weight REAL NOT NULL DEFAULT 1.0,
    PRIMARY KEY (src_id, dst_id, relation),
    FOREIGN KEY (src_id) REFERENCES experiences(id) ON DELETE CASCADE,
    FOREIGN KEY (dst_id) REFERENCES experiences(id) ON DELETE CASCADE
);

-- Freeform memory chunks (replaces MEMORY.md / USER.md §-separated prose)
CREATE TABLE memory_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,                   -- "memory" | "profile" | "fact"
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    chunk_index INTEGER NOT NULL DEFAULT 0,
    embedding BLOB,                         -- optional: ChromaDB vector
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX idx_memory_source ON memory_chunks(source);
```

### 7.4 Lifecycle State Machine

```
                    ┌─────────────┐
                    │   active    │ ◄──── created
                    └──────┬──────┘
                           │ last_used_at < now - 30 days
                           │ OR use_count = 0 AND older than 30 days
                           ▼
                    ┌─────────────┐
                    │   stale     │ ◄──── explicit set_state
                    └──────┬──────┘
                           │ last_used_at < now - 90 days
                           │ AND state = 'stale'
                           ▼
                    ┌─────────────┐
                    │  archived   │ ───► (excluded from index injection)
                    └─────────────┘

  Pinned: any state → bypasses all auto-transitions
  Reactivation: use_count++ on stale → auto-promote back to active
```

Pure SQL transitions (no `mv` / no filesystem):

```sql
-- Mark stale
UPDATE experiences
SET state = 'stale'
WHERE pinned = 0
  AND state = 'active'
  AND (
    (last_used_at IS NOT NULL AND last_used_at < datetime('now', '-30 days'))
    OR (use_count = 0 AND created_at < datetime('now', '-30 days'))
  );

-- Archive
UPDATE experiences
SET state = 'archived'
WHERE pinned = 0 AND state = 'stale'
  AND last_used_at < datetime('now', '-90 days');
```

### 7.5 LLM Interaction: Two-Tier Loading

**Tier 1 — Index in system prompt** (every turn, ~600 chars for 20 experiences):

```
## Experiences (call experience_view(name="...") to load full body)
  file-management:
    - download-organizer: Auto-classify Downloads by type and date.
    - workspace-cleanup: Weekly archive of stale project directories.
  coding:
    - pr-review-checklist: Personal PR review standards and edge cases.

Only N experiences active. Use experience_view() to load the full procedure
when a task matches. Token cost ≈ 60 chars per experience in the index.
```

**Tier 2 — `experience_view` tool** (on-demand, only when LLM judges relevant):

```python
class ExperienceViewTool(Tool):
    name = "experience_view"
    risk_level = "SAFE"

    async def execute(self, *, name: str) -> str:
        """Load full experience body + templates + scripts + references."""
        exp = self._store.get_by_name(name)
        if exp is None:
            return f"Experience '{name}' not found."
        self._store.bump_use(name)  # increments use_count, updates last_used_at
        parts = [
            f"# {exp.name}",
            f"\n## Procedure\n{exp.body}",
        ]
        for tpl in exp.templates:
            parts.append(f"\n## Template: {tpl.name}\n```\n{tpl.content}\n```")
        for scr in exp.scripts:
            parts.append(f"\n## Script: {scr.name} ({scr.language})\n```{scr.language}\n{scr.content}\n```")
        for ref in exp.references:
            parts.append(f"\n## Reference: {ref.title}\n{ref.body}")
        return "\n".join(parts)
```

### 7.6 Auto-Promotion Pipeline (P5 → P6 Bridge)

`TaskReflector` output feeds `ExperienceStore.propose_from_reflections()`:

```
task_reflections.suggested_strategy  ──►  COUNT occurrences
                                            │
                                            ▼
                              threshold ≥ 3 same-strategy cluster
                                            │
                                            ▼
                              ProposedExperience (user_id=None)
                                            │
                              ┌─────────────┼──────────────┐
                              ▼             ▼              ▼
                        /learn auto     user confirms   intensity=high
                        (skip)          via /review     auto-promote
```

```python
class ExperienceStore:
    def propose_from_reflections(self, *, threshold: int = 3) -> list[ProposedExperience]:
        """Scan task_reflections, surface repeated suggested_strategy as proposals."""
        # SQL: GROUP BY suggested_strategy HAVING COUNT(*) >= threshold
        ...

    def auto_promote(self, *, threshold: int = 3) -> int:
        """intensity=high only — create experience row from confirmed proposals."""
        ...
```

### 7.7 Memory Chunks

Freeform long-form memory, separate from `user_model.preferences` (scalar KV):

```python
class MemoryChunkStore:
    def add(self, *, source: str, title: str, body: str) -> int:
        """Save a memory chunk. Optionally indexed in ChromaDB."""
        ...

    def recall(self, query: str, *, top_k: int = 3,
               source_filter: list[str] | None = None) -> list[MemoryChunk]:
        """Vector + keyword hybrid retrieval."""
        ...

    def split_prose(self, prose: str) -> list[MemoryChunk]:
        """Parse §-separated MEMORY.md prose into chunks."""
        ...
```

`memory_chunks` complements `user_model.preferences`:
- **preferences** — scalar (editor=vscode, language=Chinese)
- **memory_chunks** — narrative (User mentioned 2024-03-15 that project A uses Postgres 14)

### 7.8 Key Differences from Hermes (Non-Copy Points)

| Aspect | Hermes | FSAR p6 |
|---|---|---|
| Skill body storage | File (`SKILL.md`) | DB row (`experiences.body`) |
| Telemetry | Sidecar JSON (`.usage.json`) | Inline columns |
| Archive action | `mv skill/ .archive/` | `UPDATE … SET state='archived'` |
| Trigger patterns | YAML frontmatter | JSON column |
| Consolidation | LLM umbrella-building pass | Pure SQL clustering (no LLM) |
| Background fork | AIAgent fork per turn | Sync only, no fork |
| Skill management surface | `skill_manage` tool exposed to LLM | API-only, not exposed to LLM |
| Memory | `MEMORY.md` prose file | `memory_chunks` table |
| Vector retrieval | Lexical overlap only | ChromaDB native (SQL + vector hybrid) |
| Multi-device sync | rsync directory tree | rsync single `.db` file |
| Description length | Hard ≤60 char rule (cache-friendly) | Soft truncate at render time |

### 7.9 Two-Tier Token Model (vs Hermes)

|  | Hermes | FSAR p6 |
|---|---|---|
| Index per-turn cost | ~60 chars × N experiences | Same (same render format) |
| Body loading | `skill_view()` tool | `experience_view()` tool |
| Token cost when unused | 0 | 0 |
| Token cost when used | 100-200 lines / body | Same (same content) |
| Auto-archive via SQL | No (LLM curator pass) | Yes (pure UPDATE) |
| Focus mode (compact_categories) | Demotes desc to names-only | Same (SQL `WHERE category IN (...)`) |

---

## 8. Risk Assessment

| Level | Description | Action |
|---|---|---|
| `SAFE` | Read file, search, query | Execute silently |
| `LOW` | Write new file, create dir | Execute + log |
| `MEDIUM` | Modify/delete file, run command | Notify user |
| `HIGH` | System ops, registry, network | Wait for confirmation |
| `CRITICAL` | Batch delete, permission changes | Warn + double confirm |

Trust model: users can promote/demote risk levels for specific operations.

---

## 9. Project Structure

```
FSAR/
├── docs/
│   └── DESIGN.md              # This document
│
├── src/
│   ├── computer_use/          # Computer Use engine (self-built)
│   │   ├── __init__.py
│   │   ├── snapshot.py        # UIA tree walk + element indexing
│   │   ├── screen_capture.py  # PrintWindow/BitBlt/DWM + grid overlay
│   │   ├── input_actions.py   # Click/type/key/scroll (SendInput/PostMessage/UIA)
│   │   └── window_manager.py  # Window enum, launch, find, kill
│   │
│   ├── orchestrator/          # Agent loop
│   │   ├── __init__.py
│   │   ├── fsar_orchestrator.py  # Main loop with function calling
│   │   └── cua_client.py      # Alternative: external CUA driver
│   │
│   ├── memory/                # Memory system
│   │   ├── __init__.py
│   │   ├── short_term.py      # In-memory conversation context
│   │   └── long_term.py       # SQLite persistence
│   │
│   ├── tools/                 # Tool system (Phase 1.5)
│   │   ├── __init__.py
│   │   ├── registry.py
│   │   └── builtin/
│   │
│   ├── mcp/                   # MCP client (Phase 3.5)
│   │   └── ...
│   │
│   ├── skills/                # Skills engine (Phase 4.5)
│   │   └── ...
│   │
│   └── utils/
│       ├── config.py
│       └── logger.py
│
├── config/
│   └── settings.yaml
│
├── data/
│   └── memory.db
│
├── main.py                    # CLI entry point
├── requirements.txt
└── README.md
```

---

## 10. Development Roadmap

> **Lesson learned:** Computer Use was implemented first as the core differentiator, but it's the hardest and least reliable tool. Most tasks that seem like they need GUI automation can be solved more reliably with shell commands, URL schemes, or file operations. Foundation tools should come first.

### Phase 1: Foundation Tools
- [x] Tool registry (ToolRegistry) — register/discover tools, OpenAI function calling format
- [x] `run_command` — shell/powershell execution with timeout
- [x] `file_ops` — read/write/list/move/delete files
- [x] `web_search` — search engine query (DuckDuckGo/Bing API)
- [x] `web_fetch` — fetch webpage content
- [x] `app_control` — launch apps via URL scheme / `start` command / ShellExecute
- [x] Orchestrator integration — LLM selects tools via function calling, results fed back

### Phase 2: Security Layer
- [x] Risk assessment engine (5 levels: SAFE → CRITICAL)
- [x] Trust model (permissions.yaml)
- [x] Tool-level permissions
- [x] Operation confirmation mechanism
- [x] Audit logging

### Phase 3: Memory System
- [x] ChromaDB semantic memory (`src/memory/semantic.py`)
- [x] User model / preferences (`src/memory/user_model.py`)
- [x] Memory recall interface (`src/memory/recall.py`)
- [x] Cross-session experience learning (`src/memory/reflection.py`)
- [x] RLHF feedback (rating + reason) — 每条回复可打分 (`src/memory/feedback.py`)
- [x] Idle reflection — 长时间不用时自动复盘 (`src/memory/reflection.py`)

### Phase 4: MCP Support
- [x] MCP Client (stdio/SSE transport)
- [x] Auto-discover tools from MCP servers
- [x] Integrate MCP tools into ToolRegistry

### Phase 5: Self-Evolution
- [x] Reflection loop (per-task + daily) — TaskReflector (per-task + on_failure, intensity gated) + ReflectionStore (task_reflections table) — see `src/memory/reflection.py`
- [x] Decision quality tracking — DecisionLog + `decision_log` table + `tool_stats` view + `@track_decision` decorator (auto-wired via ToolRegistry) — see `src/memory/decision_log.py`, `src/utils/decorators.py`. CLI: `/stats`, `/stats tool <name>`, `/stats recent`.
- [x] Execution strategy optimization — StrategyInjector synthesizes `## Learned Strategies` from tool_stats + user_model + recent task reflections, gated by `memory.reflection_intensity` (off/low/medium/high) — see `src/core/strategy_injector.py`. Wired into system prompt in `_handle_tool_task` and `_handle_chat`.

### Phase 6: Experience Layer (DB-First)
> See §7 for full design. Procedural knowledge + memory chunks as SQLite rows. Two-tier LLM loading (index in system prompt, body via `experience_view` tool). No filesystem, no sidecar JSON.
- [ ] **p6.1** Schema + `ExperienceStore` / `MemoryChunkStore` (6 tables: experiences, experience_templates, experience_scripts, experience_references, experience_links, memory_chunks)
- [ ] **p6.2** `experience_view` tool (LLM on-demand full-body loader with use_count bump)
- [ ] **p6.3** `/learn` command (conversation → experience row + auto-extracted templates/scripts/references)
- [ ] **p6.4** System prompt index injection (experiences + memory chunks, ≤60 char desc per row, compact_categories support)
- [ ] **p6.5** Auto-promotion pipeline (TaskReflector `suggested_strategy` ≥3 occurrences → `propose_from_reflections` → user confirms or `auto_promote` at intensity=high)
- [ ] **p6.6** Lifecycle SQL state machine (active → stale → archived, pure UPDATE, pinned bypass)
- [ ] **p6.7** ChromaDB embedding integration (vector + keyword hybrid retrieval on `experiences` and `memory_chunks`)
- [ ] **p6.8** Tests + end-to-end (unit tests + e2e covering /learn → store → index → view → archive)

### Phase 7: GUI
- [ ] Tauri + React frontend
- [ ] Chat panel + operation confirmation
- [ ] Memory browser
- [ ] Settings + permissions management

### Phase 8: Computer Use (Polish & Integration)
> Existing implementation at `src/computer_use/`. Deferred to last phase — hardest and least reliable tool, only needed for GUI-only scenarios. Will be polished and integrated as a ToolRegistry tool.
- [x] UIA tree walk + element indexing
- [x] Screen capture (PrintWindow/BitBlt/DWM)
- [x] Grid overlay for coordinate precision
- [x] Input actions (click/type/key/scroll)
- [x] SendInput foreground fallback (Chromium/WPF/Qt/GTK)
- [x] Window manager (launch/find/kill)
- [x] Orchestrator with function calling (OpenAI tools API)
- [x] Per-window screenshot + coordinate conversion (CUA approach)
- [ ] Better initial window detection (search by app name, not just foreground)
- [ ] Retry logic for failed clicks
- [ ] Integration with ToolRegistry as a tool
- [ ] LLM prompt tuning for mimo-v2.5

---

## 11. Technical Dependencies

```
# Core
openai>=1.0              # LLM API (function calling)
uiautomation>=2.0        # Windows UIA tree
Pillow>=10.0             # Image processing
pywin32>=300             # Win32 API (ShellExecute, etc.)

# Memory
chromadb>=0.4            # Vector memory (Phase 3)
sqlite3                  # Built-in, structured memory

# Communication
websockets>=12.0         # GUI communication
fastapi>=0.100           # WebSocket server

# Config
pyyaml>=6.0
python-dotenv>=1.0
loguru>=0.7
```

---

*Document version: 0.6 | Last updated: 2026-07-01*
*Updated: Phase 5 fully implemented (Reflection Loop + Decision Quality Tracking + Strategy Optimization — all checked off); Phase 4 (MCP Support) retroactively checked off (already implemented); Phase 6 redesigned as DB-first Experience Layer replacing the original YAML Skills System plan (see §7 for full schema, two-tier loading model, and Hermes-comparison rationale)*

# FSAR Desktop GUI — Phase 7 Design Spec

> **Status:** Draft awaiting user review
> **Date:** 2026-07-03
> **Scope:** Full desktop GUI for FSAR (7 pages)
> **Authoring constraint:** Open-source ready. Generic code, generic comments, no proprietary references. Config files may contain user-specific values.

---

## 1. Goals & Non-Goals

### Goals

- Provide a native desktop GUI that exposes every backend capability (chat, tools, memory, reflection, experiences, decision stats, token usage).
- Support **multiple LLM providers** with runtime switching from the chat topbar.
- Make the entire configuration **editable in two ways**: the GUI (Settings) **or** the unified config file (`config/fsar.yaml`). Both are first-class.
- Reach a visual standard that feels like a polished tool (Linear/Vercel tier), not a templated AI demo.
- Ship with the existing CLI as an alternative entry point; the GUI does not replace it.

### Non-Goals (this spec)

- No cloud sync, no multi-user, no remote backend. Local-first only.
- No mobile / web build. Desktop only.
- No plugin authoring IDE (plugin management UI ships, plugin authoring is external).
- No Computer Use live-debug surface (replaced by the Usage page).
- No "Companion" chat mode beyond a placeholder (gated behind a future phase).

---

## 2. Information Architecture

Seven pages, in nav order. Global Sidebar is always visible (240px, fixed, non-collapsible). Topbar holds model switcher, theme toggle, user avatar.

| # | Page | Backend surface exposed | Status |
|---|------|-------------------------|--------|
| 1 | **Chat** | Orchestrator + ToolRegistry + RiskEngine + Rate + Memory recall | Full |
| 2 | **Reflection** | TaskReflector + ReflectionStore + StrategyInjector | Full (signature page) |
| 3 | **Memory** | LongTermMemory + SemanticMemory + UserModel + ExperienceStore (chunks) | Full |
| 4 | **Library** | ExperienceStore (experiences + templates + scripts + refs + links) | Full |
| 5 | **Insights** | DecisionLog + tool_stats + ReflectionStore + StrategyInjector | Full |
| 6 | **Settings** | FsarConfig (read/write) + PermissionState + MCPManager | Full |
| 7 | **Usage** | DecisionLog (token columns) + L1/L2 cache stats + provider pricing | Full |

---

## 3. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Tauri 2 shell (Rust)                                       │
│   • Window + system tray + global shortcuts                 │
│   • Spawns Python backend as a sidecar on startup           │
│   • Manages config file lock (fcntl / msvcrt)               │
└──────────────────────────┬──────────────────────────────────┘
                           │ WebSocket (ws://127.0.0.1:8765)
┌──────────────────────────▼──────────────────────────────────┐
│  React 18 + TypeScript + Vite (SPA)                         │
│   • Tailwind v4 + shadcn/ui + Lucide                        │
│   • Zustand (per-domain stores)                             │
│   • Motion (animations)                                     │
│   • react-router (7 routes)                                 │
│   • matchMedia('prefers-color-scheme') for system theme     │
└─────────────────────────────────────────────────────────────┘
```

### Directory layout (new code)

```
frontend/                           # NEW
├── src/
│   ├── app.tsx                     # Router root
│   ├── main.tsx
│   ├── pages/
│   │   ├── Chat.tsx
│   │   ├── Reflection.tsx
│   │   ├── Memory.tsx
│   │   ├── Library.tsx
│   │   ├── Insights.tsx
│   │   ├── Settings.tsx
│   │   └── Usage.tsx
│   ├── components/
│   │   ├── shell/{Sidebar,Topbar,Layout}.tsx
│   │   ├── ui/                     # shadcn wrappers
│   │   ├── reflection/{IntensitySegment,ModeToggle,ThresholdInput,ReflectionStream}.tsx
│   │   └── chat/{MessageList,ToolCallCard,RiskConfirm,ModeSwitch,SlashPopover}.tsx
│   ├── stores/{ws,settings,ui,chat,reflection,memory,library,insights,usage}.ts
│   ├── lib/{ws-client,theme,cn,file-upload,api-key-mask}.ts
│   └── styles/globals.css
├── tailwind.config.ts
├── vite.config.ts
├── tsconfig.json
└── package.json

src/server/                         # NEW (currently empty)
├── __init__.py
├── ws_server.py                    # FastAPI + websockets, port 8765
├── handlers/
│   ├── chat.py                     # routes to Orchestrator
│   ├── reflection.py
│   ├── memory.py
│   ├── library.py
│   ├── insights.py
│   ├── usage.py
│   ├── settings.py
│   ├── mcp.py
│   └── risk.py                     # WS-driven confirm/replace for CLI input()
├── events.py                       # Shared TS/Python type definitions
└── risk_bridge.py                  # Async bridge for ConfirmResult

src/utils/fsar_config.py            # NEW: unified config (replaces src/utils/config.py)
src/utils/llm_factory.py            # REFACTOR: remove "primary" defaults, require provider_id
src/utils/decorators.py             # UNCHANGED
src/orchestrator/fsar_orchestrator.py  # REFACTOR: model kwarg no default, no hardcoded strings

config/
├── fsar.yaml                       # NEW (replaces settings.yaml + permissions.yaml)
├── settings.yaml                   # DELETED (migration in §9)
├── permissions.yaml                # DELETED (migration in §9)
└── .env                            # SHRUNK to optional boot defaults only
```

---

## 4. Per-Page Design

### 4.1 Chat (default landing page)

#### Idle state (no active conversation)

```
┌────────┬────────────────────────────────────┬─────────────────┐
│  nav   │                                    │                 │
│        │            ◯ ◯ ◯                   │                 │
│  240px │           ◯   ◯                    │                 │
│        │            ●                       │                 │
│        │       (black hole icon)            │   collapsed     │
│        │                                    │   [ › ]         │
│        │   {display_name}, 下午好。          │                 │
│        │   准备好了吗？                     │                 │
│        │   今天我们干点什么？                │                 │
│        │                                    │                 │
│        │   ┌────────────────────────────┐   │                 │
│        │   │ 📎  Ask FSAR anything…   ↵ │   │                 │
│        │   └────────────────────────────┘   │                 │
│        │                                    │                 │
└────────┴────────────────────────────────────┴─────────────────┘
```

- **Center icon**: Black hole SVG (concentric rings + central filled circle). Pure B&W. See `frontend/src/components/ui/BlackHole.tsx`.
- **Greeting text**: Time-of-day template with `{display_name}`, `{today_session_count}`, `{recent_topic}` substitutions. Falls back to generic copy when variables are empty.
- **Right rail**: Default collapsed. Click `›` to slide in (240px, 240ms).
- **Input**: 80px tall. `📎` button for file attach. Drag-drop anywhere on chat area.

#### Active state (user has sent ≥1 message)

```
┌────────┬────────────────────────────────────┬─────────────────┐
│  nav   │  ← Back to home       [+ New]      │  Recent    [ ‹ ] │
│        │                                    ├─────────────────┤
│  240px │   USER · 14:28                     │ TODAY           │
│        │   给 sunny 发个微信                  │  · 微信消息     │
│        │   ─────────────────────────        │  · 整理 Downloads│
│        │   ASSISTANT · 14:28                │ YESTERDAY       │
│        │   好的，正在打开微信…                │  · 写周报      │
│        │   ┌─ launch_app ──── [SAFE] ─┐    │ EARLIER         │
│        │   │ ▸ 微信                     │    │  · 2026-06-30  │
│        │   │   ⌄                       │    │  · ...         │
│        │   └───────────────────────────┘    │                 │
│        │                                    │                 │
│        │   ┌─ type_text ────── [MEDIUM] ─┐  │                 │
│        │   │ ▸ "在吗"                    │  │                 │
│        │   │   ⚠ Could send to wrong...  │  │                 │
│        │   │   [Edit][Cancel][Send]      │  │                 │
│        │   └───────────────────────────┘    │                 │
│        │                                    │                 │
│        │   消息已发送 ✓                     │                 │
│        │                          ☆☆☆☆☆   │                 │
│        │   ┌────────────────────────────┐   │                 │
│        │   │ 📎  Ask FSAR anything…   ↵ │   │                 │
│        │   └────────────────────────────┘   │                 │
└────────┴────────────────────────────────────┴─────────────────┘
```

- **Topbar model switcher**: Dropdown listing all enabled providers; current one marked. Selecting fires `llm.provider_changed` WS event; frontend confirms before switching on active session.
- **Messages**: Left-aligned, no bubbles. Sender label uppercase + timestamp muted. 1px hairline separator between messages.
- **Tool call card**: 1px border, mono font. Default collapsed (single-line summary); click `⌄` to expand showing `INPUT` + `OUTPUT`. Risk badge always visible top-right (`SAFE`/`LOW`/`MEDIUM`/`HIGH`).
- **Risk confirm (MEDIUM/HIGH)**: Inline blocking. Buttons: `[Edit message]` (opens message in input), `[Cancel]`, `[Send anyway]`. HIGH has 60s auto-cancel timeout.
- **Rate UI**: 5 stars at end of each assistant message. Click star to fill; expand to allow reason textarea + submit.
- **Mode toggle** (top-right of topbar): Pill `Agent` / `Companion`. Companion is **grayed and tooltip "Available in a future phase"** — selection is not wired.
- **Slash popover**: Typing `/` at line-start or after whitespace opens 480×280 popover above input. Shows 4 most-used commands + scroll for more. Type `/<filter>` to filter. `↑/↓` to navigate, `Enter` to select, `Esc` to dismiss.

#### Thinking animation

During `chat.thinking` (no first delta yet): a single small black ball pulses — scale 1.0 → 1.3 → 1.0, 0.9s ease-in-out loop. Reduced-motion users see static 0.6 opacity dot.

During `chat.tool_call` (awaiting result): same pulse resumes.

During `chat.delta`: ball fades out (180ms).

---

### 4.2 Reflection (signature page)

```
┌──────────────────────────────────────────────────────────────┐
│  Reflection                                                  │
│  Self-evolving calibration                                   │
│                                                               │
│                       REFLECTION INTENSITY                   │
│                                                               │
│              ┌─────────┬─────────┬─────────┬─────────┐       │
│              │   OFF   │   LOW   │  MEDIUM │   HIGH  │       │
│              └─────────┴─────────┴─────────┴─────────┘       │
│                            ▲ solid fill                       │
│                                                               │
│       medium · per-task + on-failure                         │
│                                                               │
│   ───────────────────────────────────────────────────────    │
│                                                               │
│   TRIGGER MODES                                               │
│                                                               │
│   ▣  Per-task             every task end                      │
│   ▢  On-failure           failed / timed-out / low-score      │
│   ▣  Idle-batch           accumulate, reflect periodically    │
│      └─ trigger when [ 20 ] events  or  [ 12 ] hours         │
│                                                               │
│  ────────────────────────────────────────────────────────    │
│                                                               │
│  Recent reflections                                           │
│                                                               │
│  14:32  send wechat to sunny                                  │
│         success · app_control, type_text                      │
│         ▸ confirm-window-before-type for WeChat message bodies│
│                                                               │
│  14:18  organize Downloads                                    │
│         partial · file_ops, run_command                       │
│         ▸ pitfall: skip .crdownload files (incomplete)        │
│                                                               │
│  ...                                                          │
└──────────────────────────────────────────────────────────────┘
```

- **Intensity segmented**: Centered, top of page. Active tab solid fill; others outline only. Transition: 200ms ease-out border→fill.
- **Explanation line**: Immediately below intensity. Dynamically describes current intensity's behavior (driven by `reflection.intensity` + triggers).
- **Trigger modes**: Three square toggles (`▣`/`▢`). Below each: short description. Idle-batch row expands inline threshold inputs only when enabled.
- **Recent reflections**: High-density list. Mono timestamps, sans body, mono strategy/pitfall tags. New entries slide in from top (240ms). Hover reveals `View ›`.

---

### 4.3 Memory

```
┌──────────────────────────────────────────────────────────────┐
│  Memory                                                      │
│  Everything FSAR remembers about you                         │
│                                                               │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ 🔍 Search memory (semantic + keyword)         ↵      │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                               │
│  PROFILE                              [View all 14 prefs →]  │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ {display_name} · {language} · {working_hours} · ...  │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                               │
│  SESSIONS · 47                          [This week ▾]       │
│  TODAY · YESTERDAY · THIS WEEK · EARLIER                    │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ 微信消息            14:28 · 6 msgs              ▸    │    │
│  │ 整理 Downloads      10:15 · 12 msgs             ▸    │    │
│  │ ...                                                  │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                               │
│  FACTS · 12                                [+ Remember]     │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ "{chunk body}"                                       │    │
│  │   {date}                                       ⌄     │    │
│  └─────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
```

- **Search**: Single input, semantic + keyword hybrid via `MemoryRecall.recall_for_context()`. On submit, sections below fold and results render inline (top 5 with score). `Esc` clears.
- **Session click**: Opens modal (80% viewport width, max 720px) with full transcript (user + assistant + tool calls collapsed inline). Footer: `[Delete session]`.
- **+ Remember**: Opens popover with text input + `[Save]` button. Saves to `memory_chunks` via `ExperienceStore.add_chunk(source="memory")`.

---

### 4.4 Library

List view (default):

```
┌──────────────────────────────────────────────────────────────┐
│  Library                                                     │
│  Procedures and skills FSAR has learned                      │
│                                                               │
│  ┌── Category ────────┬── State ───────────────────────┐    │
│  │ ▣  All       24   │ ▣  Active        20             │    │
│  │ ▢  file-mgmt  8   │ ▢  Stale          3             │    │
│  │ ▢  coding     7   │ ▢  Archived       1             │    │
│  │ ▢  research   5   │                                 │    │
│  │ ▢  workflow   4   │                                 │    │
│  └────────────────────┴─────────────────────────────────┘    │
│                                                               │
│  # download-organizer             file-management        📌  │
│  Auto-classify Downloads by type and date.                   │
│  used 47× · last 2h ago                                      │
│  ───────────────────────────────────────────────────────    │
│  # workspace-cleanup               file-management           │
│  Weekly archive of stale project directories.                │
│  used 12× · last 3d ago                            [stale]   │
│  ───────────────────────────────────────────────────────    │
│  ...                                                         │
│                                                              │
│                                              [+ Learn]       │
└──────────────────────────────────────────────────────────────┘
```

Detail view (inline replacement of list):

```
┌──────────────────────────────────────────────────────────────┐
│  ← Library                                                   │
│                                                               │
│  # download-organizer             file-management        📌  │
│  Auto-classify Downloads by type and date.                   │
│  used 47× · last 2h ago · created 2026-04-12                 │
│                                                               │
│  ┌─ Procedure ─ Body ─ Templates ─ Scripts ─ Refs ─ Links ─┐│
│  │ Procedure                                                ││
│  │                                                          ││
│  │ ## Goal                                                  ││
│  │ ...                                                      ││
│  └─────────────────────────────────────────────────────────┘│
│                                                               │
│                          [Edit]  [Archive]  [Unpin]          │
└──────────────────────────────────────────────────────────────┘
```

Learn / Edit modal: name + category (dropdown of existing + freeform) + description + body (markdown editor) + collapsible templates/scripts/references sections.

---

### 4.5 Insights

```
┌──────────────────────────────────────────────────────────────┐
│  Insights                                                    │
│  What FSAR has learned and how it's performing               │
│                                                               │
│  ┌────────┬────────┬────────┬────────┐                      │
│  │  247   │  89%   │  12.4k │  1.2s  │                      │
│  │ total  │ success│ tokens │ avg    │                      │
│  │ tasks  │  rate  │ /task  │ /tool  │                      │
│  └────────┴────────┴────────┴────────┘                      │
│                                                               │
│  TOOL USAGE                              [This week ▾]     │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ Tool           Calls  Succ  Avg  Last               │    │
│  │ file_ops          87  94%  0.3s  2m ago              │    │
│  │ run_command       54  98%  1.1s  14m ago             │    │
│  │ app_control       42  76%  0.8s  1h ago   [low]      │    │
│  │ ...                                                  │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                               │
│  REFLECTIONS                            [All time ▾]       │
│  ┌──────────┬──────────┬──────────┐                         │
│  │ 47       │ 12       │ 3        │                         │
│  │ triggered│ active   │ proposed │                         │
│  └──────────┴──────────┴──────────┘                         │
│                                                               │
│  ACTIVE STRATEGIES                                           │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ ## Learned Strategies                                │    │
│  │ - confirm-window-before-type for WeChat message ...  │    │
│  │ - skip .crdownload files (Chrome in-progress)        │    │
│  │ ...                                                  │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                               │
│  RECENT DECISIONS                       [View all 247 →]    │
│  ...                                                          │
└──────────────────────────────────────────────────────────────┘
```

- Tool rows with `success_rate < 80%` get a `[low]` text badge (no color).
- "Active Strategies" calls `StrategyInjector.build_block()` server-side and renders the resulting markdown.

---

### 4.6 Settings (5-tab view over `fsar.yaml`)

Tabs (left sub-sidebar 200px): Models / Reflection / Permissions / MCP / Style / Advanced

#### Models tab

```
│  Active provider                                              │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ ▼ {active_provider.label}                  [default] │    │
│  └──────────────────────────────────────────────────────┘    │
│  affects Chat, Reflection insights, tool selection           │
│                                                               │
│  Configured providers (N)                       [+ Add]      │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ ● {label}     {provider_family}                       │    │
│  │   base_url: {host}    model: {model}                 │    │
│  │   key: ●●●●●●●●● [show]                              │    │
│  │   [Edit] [Test] [Set default] [Delete]               │    │
│  ├──────────────────────────────────────────────────────┤    │
│  │ ○ ...                                                 │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                               │
│  Embedder                                                     │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ provider [lmstudio ▾] base_url [...] model [...]    │    │
│  │ timeout [60]s                                        │    │
│  │ [Test connection]   ✓ Connected · 142ms              │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                               │
│  LLM cache                                                    │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ Enabled [●]  L1 entries [256]  L1 TTL [300]s        │    │
│  │ L2 TTL [86400]s  Skip vision [●]                    │    │
│  └──────────────────────────────────────────────────────┘    │
```

**Edit / Add provider modal** has fields: label / provider_family / base_url / api_key / model / pricing / enabled. `[Test connection]` button does a lightweight model-list ping.

#### Reflection tab

Mirror of the Reflection page controls (intensity + triggers + thresholds). All writes go to `fsar.yaml` `reflection:` section.

#### Permissions tab

```
│  Tool Risk Overrides                                          │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ Tool            Default  Yours   Override             │    │
│  │ run_command     HIGH     HIGH    [▾]                  │    │
│  │ delete_file     HIGH     MED     [▾]  ← demoted       │    │
│  │ ...                                                  │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                               │
│  Confirmation behavior                                        │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ HIGH timeout [60]s                                   │    │
│  │ MEDIUM default action [Ask me ▾]                     │    │
│  │ Rating prompt [●]                                    │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                               │
│  Path rules                                                   │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ Pattern                              Action          │    │
│  │ C:\Windows.*                         deny            │    │
│  │ [+ Add rule]                                          │    │
│  └──────────────────────────────────────────────────────┘    │
│                                              [Reset to default]│
```

#### MCP tab

List of `mcp.servers[*]` rows with `enabled` toggle, transport, command, risk_level, `[Tools ▾]` (expands to show tools + their risk), `[Reload]` (re-spawn server), `[Stop]`, `[Edit]`. `[+ Add server]` opens a modal. All edits round-trip through `fsar.yaml`.

#### Style tab

Global: theme (LIGHT / DARK / SYSTEM), font scale slider, density (Compact / Comfortable), motion (None / Subtle / Full).

Per-page overrides (each page exposes its toggleable behaviors; see §4.1–4.7 for the per-page list).

#### Advanced tab

- **Audit log**: last 50 entries from `decision_log` (`tool · risk · outcome · timestamp`).
- **Raw YAML view**: read-only display of the loaded `fsar.yaml`. `[Open in editor]` opens the file in the OS default editor.
- **Danger zone**: `[Reset all settings to default]` (writes minimal yaml with default values; irreversible). `[Export config]` (download yaml).

#### Topbar universal

Model switcher is duplicated in topbar for one-click switching without leaving Chat. Same dropdown content as Settings → Models → Active provider.

---

### 4.7 Usage

```
┌──────────────────────────────────────────────────────────────┐
│  Usage                                                       │
│  Token consumption and cost                                  │
│                                                               │
│  ┌────────┬────────┬────────┬────────┐                      │
│  │ 12.4k  │ 3.1k   │ 68%    │ $0.42  │                      │
│  │ tokens │cached  │cache   │ est.   │                      │
│  │ /task  │ /task  │ hit %  │ cost   │                      │
│  └────────┴────────┴────────┴────────┘                      │
│                                                               │
│  TIMELINE · tokens/day   [Tokens ▾] [30 days ▾]            │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ ▆▆▅▇▆▄▃▅▇█▆▅▄▃▂▃▄▅▆▇█▇▆▅▄▃▂▃▂▃▄▅▆▇█▇▆                │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                               │
│  PER-PROVIDER                                                 │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ Provider         Calls  In/Out       Cache hit       │    │
│  │ {active}            187  1.2M/380k    72%            │    │
│  │ ...                                                  │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                               │
│  PER-TOOL  (top 10 by tokens)         [This week ▾]        │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ Tool           Calls  Tokens  Avg/call  Cache hit    │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                               │
│  CACHE BREAKDOWN                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ L1 (memory)   256 entries · 5 min TTL · 24% hit    │    │
│  │ L2 (disk)   12,847 entries · 24 h TTL · 44% hit    │    │
│  │ Provider cache  varies by family                    │    │
│  │ [Flush L1]  [Flush L2]  [Disable caching]           │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                               │
│  COST FORECAST                                               │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ This week   $3.20 (estimated)                        │    │
│  │ This month  $14.50 (estimated)                       │    │
│  │ Pricing configured per provider in Models tab.       │    │
│  └─────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
```

Token totals come from `decision_log.prompt_tokens / completion_tokens / cached_tokens` (columns added in this spec — see §9 schema migration). Cache stats come from `LLMCache.get_stats()`. Cost = `Σ (prompt_tokens / 1000 × input_per_1k) + (completion_tokens / 1000 × output_per_1k)` grouped by provider.

---

## 5. Design System

### 5.1 Color

Light + dark + system-aware via `matchMedia('prefers-color-scheme')`. Six named tokens per theme.

**Light:**

| Token | Hex | Use |
|-------|-----|-----|
| `bg` | `#FAFAFA` | Page background |
| `surface` | `#FFFFFF` | Cards / inputs / topbar |
| `text` | `#0A0A0A` | Primary text |
| `text-muted` | `#6B6B6B` | Timestamps, captions |
| `border` | `#E5E5E5` | 1px hairlines |
| `border-strong` | `#0A0A0A` | Selected state, active toggles |

**Dark:**

| Token | Hex | Use |
|-------|-----|-----|
| `bg` | `#0E0E10` | Page background |
| `surface` | `#161618` | Cards / inputs / topbar |
| `text` | `#F5F5F7` | Primary text |
| `text-muted` | `#8A8A92` | Timestamps, captions |
| `border` | `#1F1F22` | 1px hairlines |
| `border-strong` | `#F5F5F7` | Selected state, active toggles |

No accent color anywhere. Status conveyed via text-only badges (`[low]`, `[stale]`, `[pinned]`).

### 5.2 Typography

| Role | Family | Size / weight | Letter-spacing |
|------|--------|---------------|----------------|
| Display | Geist Sans | 18px / 600 | 0 |
| H1 | Geist Sans | 24px / 600 | -0.01em |
| H2 | Geist Sans | 18px / 600 | -0.005em |
| Body | Inter | 14px / 400 | 0 |
| Body emphasis | Inter | 14px / 500 | 0 |
| Caption | Inter | 12px / 400 | 0 |
| Section label | Geist Sans | 10px / 700, uppercase | 0.1em |
| Mono | Geist Mono | 13px / 400 | 0 |
| Mono emphasis | Geist Mono | 13px / 500 | 0 |
| KPI number | Geist Sans | 32px / 600, tabular-nums | -0.02em |

### 5.3 Spacing & radius

- Base unit: 4px. Component internal padding: 16px. Section vertical spacing: 32px. Page horizontal padding: 32px.
- Border radius: 6px universal. No zero-radius elements. No large-radius pill shapes (chips are 6px).
- Border: 1px hairline by default. Hover / active states: 2px on `border-strong` token.

### 5.4 Motion

- Page transitions: 180ms ease-out cross-fade.
- Card mount: 240ms slide-up 8px + fade.
- Hover: 120ms color/border swap.
- Thinking pulse (Chat): 0.9s scale 1.0→1.3→1.0 loop.
- Stream / typewriter: per-character 30ms (existing pattern).
- All animations honor `@media (prefers-reduced-motion: reduce)` and the `style.motion` user setting.

---

## 6. Data Flow (WebSocket protocol)

Single bidirectional JSON channel. Heartbeat every 15s.

```ts
// Client → Server
type ClientMsg =
  | { type: "chat.send", content: string, mode: "agent" | "companion", attached_files?: string[] }
  | { type: "chat.cancel" }
  | { type: "chat.rate", message_id: string, score: 1|2|3|4|5, reason?: string }
  | { type: "risk.respond", call_id: string, response: "y" | "n" | "all" | "server" | "never" }
  | { type: "reflection.set_intensity", intensity: "off"|"low"|"medium"|"high" }
  | { type: "reflection.set_trigger", trigger: "per_task"|"on_failure"|"idle_batch", enabled: boolean, threshold?: { events?: number, hours?: number } }
  | { type: "settings.get" } | { type: "settings.patch", patch: Partial<FsarYaml> }
  | { type: "library.create" | "library.update" | "library.delete" | "library.archive", ... }
  | { type: "memory.search", query: string }
  | { type: "memory.remember", body: string }
  | { type: "usage.range", from: string, to: string }
  | { type: "llm.set_active", provider_id: string }
  | { type: "mcp.reload" | "mcp.toggle", server_name: string, enabled?: boolean }

// Server → Client
type ServerMsg =
  | { type: "snapshot", config: FsarYaml, runtime: { active_provider: string, theme: string, ... } }
  | { type: "chat.delta", message_id: string, content: string }
  | { type: "chat.thinking", message_id: string }
  | { type: "chat.tool_call", message_id: string, call_id: string, tool: string, args: any, risk: "SAFE"|"LOW"|"MEDIUM"|"HIGH", server_name?: string }
  | { type: "chat.tool_result", call_id: string, result: any, latency_ms: number, tokens?: { prompt: number, completion: number, cached: number } }
  | { type: "chat.done", message_id: string, outcome: "success"|"failure"|"timeout", summary?: string }
  | { type: "chat.risk_request", call_id: string, tool: string, args_preview: string, reason: string, server_name?: string }
  | { type: "chat.session_renamed", session_id: string, title: string }
  | { type: "reflection.event", event: TaskReflection }
  | { type: "reflection.intensity_changed", intensity: string, triggers: {...} }
  | { type: "settings.changed", patch: Partial<FsarYaml>, by: "user"|"file_watcher" }
  | { type: "library.changed", op: "create"|"update"|"delete", name: string }
  | { type: "memory.search_results", query: string, results: Array<{ session_id: string, snippet: string, score: number }> }
  | { type: "usage.snapshot", kpis: {...}, timeline: [...], per_provider: [...], per_tool: [...], cache: {...} }
  | { type: "llm.provider_changed", provider_id: string, model: string }
  | { type: "mcp.status", servers: Array<{ name: string, enabled: boolean, running: boolean, tools: number }> }
  | { type: "error", code: string, message: string, recoverable: boolean }
  | { type: "heartbeat", ts: number }
```

### Risk confirm wire replacement

CLI `input()` is replaced by an in-process queue:

1. Backend's `risk_handler.py` wraps `RiskEngine.evaluate()` and, on `confirm`, builds a `Future[ConfirmResponse]`.
2. `ConfirmRequest` is pushed onto a singleton asyncio.Queue and sent over WS as `chat.risk_request`.
3. Frontend renders the inline confirm card (MEDIUM/HIGH) or modal (alternative).
4. User clicks → frontend sends `risk.respond` → backend resolves the future → tool proceeds or aborts.
5. Timeout: default 60s for HIGH, 120s for MEDIUM, configurable in Settings. Auto-deny on timeout.

---

## 7. Configuration (`config/fsar.yaml`)

Single source of truth for all knobs. Settings GUI writes back to this file with an atomic rename + `.bak` backup.

### Full schema

```yaml
# LLM providers
llm:
  active: string                        # provider id
  providers:
    - id: string                        # unique
      label: string                     # display name
      provider_family: openai | openai-compatible | anthropic | gemini
      base_url: string
      api_key: string                   # literal or "${ENV_VAR}"
      model: string
      pricing:
        input_per_1k: number
        output_per_1k: number
      enabled: boolean

# Embedder
embedder:
  provider: string                      # lmstudio | ollama | openai-compatible
  base_url: string
  model: string
  timeout: number                       # seconds

# Memory
memory:
  sqlite_path: string
  short_term_window: integer
  chroma_path: string
  reflection_interval_hours: number
  reflection_intensity: off | low | medium | high
  recall_max_chars: integer
  enable_rating_prompt: boolean

# LLM cache
llm_cache:
  enabled: boolean
  db_path: string
  l1_max_entries: integer
  l1_ttl_seconds: number
  l2_ttl_seconds: number
  retention: none | short | long
  skip_vision: boolean
  use_responses_api: boolean

# GUI
gui:
  host: string
  port: integer

# Logging
logging:
  level: DEBUG | INFO | WARNING | ERROR
  file: string                          # path template

# Permissions
permissions:
  mode: strict | normal | trust
  tools:
    <tool_name>:
      risk: SAFE | LOW | MEDIUM | HIGH | CRITICAL
      mode: trust | ask | deny
      operations:
        <op_name>: trust | ask | deny
      blocked_patterns: [string, ...]
  path_rules:
    - match: regex
      action: deny | ask
      operations: [string, ...]         # empty = any

# MCP
mcp:
  servers:
    - name: string
      enabled: boolean
      transport: stdio                  # only stdio supported this phase
      command: string
      args: [string, ...]
      env: { string: string }
      cwd: string | null
      risk_level: SAFE | LOW | MEDIUM | HIGH | CRITICAL

# Reflection
reflection:
  intensity: off | low | medium | high
  triggers:
    per_task: boolean
    on_failure: boolean
    idle_batch:
      enabled: boolean
      threshold_events: integer
      threshold_hours: integer

# User profile
user:
  display_name: string

# Style
style:
  theme: light | dark | system
  font_scale: number                    # 0.85 – 1.15
  density: compact | comfortable
  motion: none | subtle | full
  per_page_overrides:
    chat:
      show_tool_io: boolean
      show_risk_badges: boolean
      auto_name_sessions: boolean
    reflection:
      pulse_animation: boolean
      show_event_stream: boolean
    memory:
      show_profile_summary: boolean
      facts_default_expanded: boolean
    library:
      detail_opens_inline: boolean
    insights:
      default_range: today | this_week | this_month | all_time

# Plugin registry (reserved for future)
plugins: []

# External skill libraries (reserved for future)
external_skills: []
```

### Boot-time path resolution

`FSAR_CONFIG_PATH` env var (in `.env`) overrides default `./config/fsar.yaml`. If the file is missing, the binary writes a default yaml with all required sections populated.

### File locking

Single writer at a time: Python uses `fcntl.flock` (POSIX) / `msvcrt.locking` (Windows). Tauri shell holds a non-blocking shared lock on startup; Settings GUI takes exclusive lock during writes.

### File watcher

Tauri shell watches `fsar.yaml` via `notify` crate. On external edit, frontend receives `settings.changed` event with `by: "file_watcher"`. Frontend applies non-conflicting patches; conflicts (mid-edit) trigger a reload dialog.

### Migration

A one-shot migration runs on first launch after upgrade:
1. Read existing `settings.yaml` + `permissions.yaml` + relevant `.env` keys.
2. Write new `fsar.yaml` with merged content.
3. Backup originals to `config/.migrated/{ts}/`.
4. Delete originals (or move if user prefers via `--keep-legacy` flag).

---

## 8. Backend Changes (no hardcoded values)

### 8.1 Remove all hardcoded provider strings

**Current (to remove):**
- `Orchestrator.__init__(self, llm_client, model: str = "mimo-v2.5", ...)` — default value is a specific model string.
- 11× `cfg.get_llm_config("primary")` — `"primary"` is a hardcoded block name.
- 3× `make_*_client("primary")` — same.
- `llm_factory.detect_provider_family()` heuristic — to be replaced by explicit `provider_family` from yaml.

**Target:**
- `Orchestrator.__init__(self, llm_client, model: str, ...)` — `model` is required, no default. Caller resolves from `FsarConfig.get_active_provider()`.
- `cfg.get_llm_config(provider_id: str)` — no default. `provider_id` always explicit.
- New `cfg.get_active_provider()` — returns `cfg.get_llm_config(cfg.get("llm.active"))`.
- `make_*_client(provider_id: str)` — no default, no `"primary"` fallback.
- `detect_provider_family()` deleted. Family is read from `provider_family` field in yaml.
- Image / PDF analyze tools: `provider_id` resolved from active config at call time, not hardcoded.

### 8.2 New `FsarConfig` class

Lives at `src/utils/fsar_config.py`. Replaces `src/utils/config.py` (the old module may remain as a thin alias for one release, then be removed).

```python
class FsarConfig:
    def __init__(self, path: str | Path | None = None): ...
    def load(self) -> None: ...                  # read from yaml
    def save(self) -> None: ...                  # atomic write + .bak
    def get(self, dotkey: str, default=None): ...
    def patch(self, dotkey: str, value): ...    # in-memory + optional save
    def get_llm_config(self, provider_id: str) -> dict: ...
    def get_active_provider(self) -> dict: ...
    def set_active_provider(self, provider_id: str): ...
    def list_providers(self, enabled_only: bool = False) -> list[dict]: ...
    def add_provider(self, p: dict) -> None: ...
    def update_provider(self, p: dict) -> None: ...
    def remove_provider(self, provider_id: str) -> None: ...
```

Locking: `save()` and patch operations acquire a process-local lock + best-effort OS file lock. Cross-process lock via `fcntl`/`msvcrt`.

### 8.3 Schema migration: `decision_log` adds token columns

```sql
ALTER TABLE decision_log ADD COLUMN prompt_tokens INTEGER NOT NULL DEFAULT 0;
ALTER TABLE decision_log ADD COLUMN completion_tokens INTEGER NOT NULL DEFAULT 0;
ALTER TABLE decision_log ADD COLUMN cached_tokens INTEGER NOT NULL DEFAULT 0;
CREATE INDEX IF NOT EXISTS idx_decision_provider_created
    ON decision_log(chosen_tool, created_at);  -- supports per-tool queries by date range
```

`@track_decision` extracts `response.usage.prompt_tokens / completion_tokens` post-call (when available; otherwise 0). Provider-specific paths in `llm_factory` populate `cached_tokens` from each family's native response.

Migration script: `src/utils/migrations/2026_07_03_decision_tokens.py`. Idempotent — checks `PRAGMA table_info` before applying.

### 8.4 `LLMCache.get_stats()`

```python
def get_stats(self) -> dict:
    return {
        "l1_entries": int,
        "l1_capacity": int,
        "l1_hit_rate": float,         # hits / (hits + misses) over lifetime
        "l2_entries": int,
        "l2_size_bytes": int,
        "l2_hit_rate": float,
    }
```

Existing `_hits`/`_misses` counters already maintained; expose them.

### 8.5 WebSocket server skeleton

`src/server/ws_server.py`:

```python
from fastapi import FastAPI, WebSocket
from src.utils.fsar_config import FsarConfig
from src.server.handlers import chat, reflection, memory, library, insights, usage, settings, mcp

app = FastAPI()
config = FsarConfig()

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    await ws.send_json({"type": "snapshot", "config": config._settings, ...})
    async for msg in ws.iter_json():
        await dispatch(msg, ws)
```

Each handler module exposes `async def handle(msg, ws, ctx) -> None`.

### 8.6 Risk confirm async bridge

`src/server/risk_bridge.py` exposes a `RiskBridge` singleton holding a `dict[str, asyncio.Future]`. The Python `ask_user()` in `confirmation.py` is refactored to accept an optional `bridge` parameter; when set, it awaits the future instead of calling `input()`. CLI mode (no bridge) keeps existing behavior unchanged.

---

## 9. Generic / Open-Source Constraints

This is an **Apache 2.0 project** (per existing project documentation). All new code must respect:

1. **No company-specific defaults in code.** Model ids, URLs, file paths, env var names must be placeholders or namespaced. Examples to avoid:
   - `"mimo-v2.5"` as a default value
   - Hardcoded URL pointing at any vendor
   - Default model strings from any specific company
   - `api.minimaxi.com` or equivalent in any non-config file
   - `cua-driver` paths as defaults
   - Comments mentioning specific products ("openclaw", "Hermes", "Anthropic-only")

2. **Comments are generic.** Code comments describe what the code does and why, not who uses it. No marketing-style comments.

3. **Config file values may be user-specific.** `fsar.yaml` shipped in the repo is a placeholder example with `example.com`, generic provider ids (`provider-a`, `provider-b`), and zero pricing. Users edit their own copy.

4. **`.env` is optional and minimal.** Only `FSAR_CONFIG_PATH` and similar boot knobs. No secrets.

5. **Test fixtures use synthetic data.** Never commit real API keys, real conversation transcripts, real tool outputs. Use fixtures named `test-fixture-*`.

6. **Error messages must be actionable but neutral.** Avoid blaming any provider by name when a generic error class suffices.

7. **License headers.** Every new source file starts with the SPDX Apache-2.0 header (consistent with the rest of the repo).

8. **i18n posture.** UI strings are English-only in this spec. Future i18n is out of scope but strings must be centralized in `frontend/src/lib/i18n.ts` from day one (not inlined).

---

## 10. Testing Strategy

### Backend

| Scope | Method |
|-------|--------|
| `FsarConfig` round-trip | pytest: write yaml → load → assert fields; patch → save → reload from disk |
| Multi-provider resolution | pytest: 2 providers in yaml, swap active, verify `get_active_provider()` and `make_llm_client(id)` correctness |
| `LLMCache.get_stats()` | pytest: prime cache, query stats, assert hit/miss counts |
| Schema migration | pytest: pre-migration sqlite → run migration → assert columns exist |
| WS handler smoke | pytest: open WS, send each `ClientMsg` type, assert matching `ServerMsg` |
| Risk bridge | pytest: trigger confirm, set future result, assert downstream proceeds |

### Frontend

| Scope | Method |
|-------|--------|
| Reflection controls | React Testing Library: 4 intensity segments render, click changes state, calls `reflection.set_intensity` |
| Slash popover | RTL: type `/`, assert popover visible with 4 items; type `/a`, assert filter applied |
| Tool call expand/collapse | RTL: collapsed by default, click expands, INPUT/OUTPUT visible |
| Settings — multi-provider | RTL: render 3 providers, click delete, confirm dialog, list updates |
| WebSocket reconnect | RTL: mock WS that closes, assert reconnect with backoff |
| Theme switching | RTL: toggle system theme via `matchMedia`, assert class swap |

### Visual / manual

- No automated visual regression tests this phase.
- Manual smoke checklist (covered in §12 implementation phases):
  - All 7 pages render with both light and dark.
  - Per-page style overrides take effect.
  - Mode switching reloads active conversation cleanly.
  - File lock prevents concurrent writes between CLI and GUI.

---

## 11. Out-of-Scope (Explicit Deferrals)

- **Companion chat mode** (Chat topbar shows grayed placeholder).
- **Web build / mobile build** of the GUI.
- **Cloud sync / multi-device**.
- **Plugin authoring IDE** (plugin install/configure only).
- **Live Computer Use debug surface** (replaced by Usage page).
- **Multi-user / auth**.
- **i18n beyond string centralization**.
- **Real-time collaborative editing** of `fsar.yaml` (file lock + reload dialog is sufficient).

---

## 12. Implementation Phases

Each phase is independently shippable behind a flag; the GUI builds but pages opt-in.

| Phase | Scope | Exit criteria |
|-------|-------|---------------|
| **P7.1** | `FsarConfig` + yaml schema + migration script + backend alias cleanup | All existing CLI commands keep working; `fsar.yaml` is the new source |
| **P7.2** | Tauri 2 shell + React skeleton + WS server + Chat page (idle + active + tool cards) | Can chat end-to-end via GUI; tool calls render |
| **P7.3** | Risk confirm bridge + HIGH/MEDIUM inline cards + rate UI + slash popover | Confirm flow works in GUI; CLI path unchanged |
| **P7.4** | Reflection page + Settings → Reflection tab + file watcher + WS `reflection.event` | Intensity / trigger changes persist to yaml and survive restart |
| **P7.5** | Memory page + Library page + WS handlers | Browse sessions, edit experiences, add facts |
| **P7.6** | Insights page + decision_log token columns + per-provider aggregation | Stats render correctly with seeded data |
| **P7.7** | Usage page + L1/L2 stats expose + pricing per provider | Cost forecast matches manual sum |
| **P7.8** | Multi-provider UI + active provider switcher + cached client invalidation on switch | Switching mid-chat cleanly hands off |
| **P7.9** | Settings → MCP tab + Permissions tab + Style tab + Advanced | All edits round-trip to yaml |
| **P7.10** | Per-page style overrides + theme system matchMedia + reduced-motion support | Style tab fully functional |

Estimated total: 10–14 weeks for one engineer.

---

## 13. Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Migration breaks existing CLI users | Backup originals; `--keep-legacy` flag; one-release deprecation warning |
| Concurrent edits to `fsar.yaml` corrupt file | File lock + atomic rename + reload dialog on conflict |
| Tauri-side cache invalidation when active provider changes | `make_llm_client(provider_id)` keyed by id; existing singletons dropped via `reset_clients()` on switch |
| Token columns backfill empty for old `decision_log` rows | Migration sets 0; analytics pages show "no data yet" hint for the first week |
| Risk confirm timeout races the user's actual response | Timeout callback resolves future with `NO`; frontend shows a brief "auto-cancelled" banner |
| GUI WS reconnect storms | Exponential backoff 1s → 30s with jitter; cap at 3 retries per minute |
| Schema additions break existing tools | `FsarConfig.get()` always returns default if missing; tools tolerate absent fields |

---

## 14. Open Questions

None blocking. Items that may want follow-up later (not in this spec):

- Should `user.display_name` also drive Tauri window title?
- Should Usage page export a CSV of token rows?
- Should Memory page support multi-session view (compare 2 sessions side-by-side)?
- Should Insights page support date-range comparison ("this week vs last week")?

---

*End of spec — please review and request changes before plan generation.*

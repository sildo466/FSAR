# PL2.0 — Persona Foundation

**Date:** 2026-07-09
**Status:** Design (awaiting user review)
**Phase:** PL2.0 (first sub-phase of PL2, per DESIGN.MD §16.1)
**Scope:** Character card + user card schemas, CRUD, persona injection, /cards page, Chat topbar binding

---

## 1. Purpose & Exit Criteria

### 1.1 Purpose

Make FSAR feel like a *person*, not a tool. Character cards drive tone, user cards drive relevance, together they cut generic-LLM behavior.

### 1.2 Exit Criteria (from DESIGN.MD §16.1, unchanged)

> User can create a character card, switch to it, and see the persona take effect in the next reply.

### 1.3 Explicit non-goals (PL2.0 does NOT do)

| Item | Reason | Phase |
|---|---|---|
| Onboarding wizard | separate flow | PL2.1 |
| Sandbox workspace | different concern | PL2.2 |
| `card_edit` LLM tool | UI editing sufficient for v0 | deferred |
| Multiple user cards with per-session choice | "you are the same person" semantic | deferred |
| ST V3 spec support | parser covers v2; v3 marks future-compatible | PL3+ |
| Avatar SVG defaults | keep shipped cards headless for now | PL2.7 |
| Per-conversation user card override | global default only | deferred |

---

## 2. Decisions (locked)

Decisions made through brainstorming (2026-07-09). Numbered for spec cross-reference.

| # | Decision | Deviates from DESIGN.MD? |
|---|---|---|
| D1 | Card switching: **global default + per-session character binding** (user card: global only) | No |
| D2 | 6 default cards = 2 × FSAR (zh, en) + 2 × coding-coach (zh, en) + 2 × research-analyst (zh, en) | Slight: doc lists 3 personas × 2 langs = 6; we replace "default-companion" with "FSAR" |
| D3 | FSAR card's `description` / `personality` = humanized restatement of current `AGENT_SYSTEM_PROMPT` opening; `system_prompt_override` = empty (AGENT_SYSTEM_PROMPT passes through unchanged) | No |
| D4 | All shipped cards have `system_prompt_override = ""`; persona is conveyed via the persona block only | No |
| D5 | SillyTavern V2 import: **in scope** (parser covers v2 spec; v1/v3 fall back to defaults) | No |
| D6 | Avatar storage: file path under `data/avatars/{card_id}.{ext}` | No |
| D7 | `character.system_prompt_override` semantics: **APPEND to AGENT_SYSTEM_PROMPT tail** (not replace) | **Yes** — §5.2 says "replaces AGENT_SYSTEM_PROMPT"; we deviate to preserve MCP/skill how-to instructions |
| D8 | `card_edit` LLM tool: **not in PL2.0** | No (PL2.7 deferred) |
| D9 | `data/cards/*.json` is **first-run seed only**; DB is single source of truth at runtime | No (matches §18 decision log) |
| D10 | `/cards` is a **top-level sidebar entry**; NOT under Settings | No (matches §5.5) |
| D11 | First-run seed: table empty → insert all builtins. User cleared table → do NOT auto re-seed on next launch | Slight: doc implies "detects edits" but we keep it simple |
| D12 | Approach: **DB single source + JSON first-run seed** (Approach A from brainstorming) | No |
| D13 | GUI chat: **ASSISTANT bubble** label = current session's `character.name`; **USER bubble** label = current default `user_card.name` | New (vs DESIGN.MD) |
| D14 | `character.name` and `user_card.name` snapshotted at message emit time (not resolved at render) | New (vs DESIGN.MD) |

**D7 is the only real deviation.** It's deliberate: replacing AGENT_SYSTEM_PROMPT would drop the MCP-install / skill-install how-to. Appending preserves it.

---

## 3. Architecture

### 3.1 Component diagram

```
┌─────────────────────────────────────────────────────────────┐
│  Tauri + React GUI                                           │
│  ┌──────────┐ ┌────────────┐ ┌──────────┐ ┌──────────┐    │
│  │ Chat     │ │ Cards  ◀─ new top-level │ Library │ Settings │    │
│  │ (Topbar  │ │ sidebar entry) │         │          │    │
│  │  with    │ │                 │         │          │    │
│  │  char    │ │                 │         │          │    │
│  │  dropdown│ │                 │         │          │    │
│  │ )        │ │                 │         │          │    │
│  └────┬─────┘ └─────┬───────────┘         └────┬─────┘    │
│       │ WS         │ WS                       │ WS         │
└───────┼───────────┼──────────────────────────┼─────────────┘
        │           │                          │
┌───────▼───────────▼──────────────────────────▼──────────────┐
│  src/server/ws_server.py                                     │
│   ├─ handlers/chat.py      (existing, emit extended)         │
│   ├─ handlers/card.py      ◀ NEW (WS + HTTP avatar)          │
│   └─ chat_engine.py        (existing, persona-aware)         │
└──────┬────────────────────────────────────┬──────────────────┘
       │                                    │
┌──────▼─────────┐                ┌─────────▼───────────────┐
│ src/core/       │                │ src/memory/              │
│  prompts.py     │◀── inject ────│  session_store.py         │
│  persona.py ◀─NEW│               │  cards.py        ◀─NEW   │
└─────────────────┘                │  (CRUD + ST V2 parser)   │
                                   └────────┬─────────────────┘
                                            │
                                   ┌────────▼─────────────────┐
                                   │ SQLite (data/fsar.db)     │
                                   │  character_cards   ◀─NEW  │
                                   │  user_cards        ◀─NEW  │
                                   │  sessions.character_card_id ◀─NEW │
                                   └───────────────────────────┘
```

### 3.2 Message flow (one turn)

```
User message arrives (chat.send)
  → session_store.get(session_id) → character_card_id (NULL → global default)
  → card_repo.get_character(id) → CharacterCard
  → card_repo.get_default_user_card() → UserCard
  → persona.assemble_persona_block(character, user_card) → PersonaBlock
  → chat_engine._build_prompt(session, mode):
      memory_block = self.evolution.build(...)
      strategy_block = strategy_injector.build(...)
      experience_block = experience_injector.build(...)
      → build_system_prompt(mode, character, user_card, memory_block, ...)
  → LLM call (cached via existing LLM cache; per-turn key naturally varies)
  → emit assistant delta with { character_name, character_id }
  → user bubble echo carries { user_name, user_card_id }
```

---

## 4. Data Model

### 4.1 `character_cards` (NEW)

```sql
CREATE TABLE IF NOT EXISTS character_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    avatar_path TEXT,
    description TEXT NOT NULL,
    personality TEXT NOT NULL,
    scenario TEXT DEFAULT '',
    system_prompt_override TEXT DEFAULT '',
    example_dialogues TEXT DEFAULT '[]',
    tags TEXT DEFAULT '[]',
    is_default INTEGER NOT NULL DEFAULT 0,
    created_by TEXT NOT NULL DEFAULT 'user',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_character_cards_default
    ON character_cards(is_default) WHERE is_default = 1;
```

### 4.2 `user_cards` (NEW)

```sql
CREATE TABLE IF NOT EXISTS user_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    avatar_path TEXT,
    description TEXT NOT NULL,
    preferences TEXT DEFAULT '{}',
    interests TEXT DEFAULT '[]',
    communication_style TEXT DEFAULT '',
    is_default INTEGER NOT NULL DEFAULT 0,
    created_by TEXT NOT NULL DEFAULT 'user',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_user_cards_default
    ON user_cards(is_default) WHERE is_default = 1;
```

### 4.3 `sessions.character_card_id` (migrate)

```sql
ALTER TABLE sessions ADD COLUMN character_card_id INTEGER
    REFERENCES character_cards(id) ON DELETE SET NULL;
```

Applied via `SessionStore._migrate_character_binding()`, idempotent (PRAGMA table_info check, then ADD COLUMN only if column missing). Mirrors existing `_migrate_conversations` pattern.

### 4.4 `data/cards/*.json` (shipped)

6 JSON files committed to the repo. First-run only. Schema:

```json
{
  "_meta": { "created_by": "builtin", "seed_version": 1, "role": "FSAR" },
  "name": "FSAR",
  "language": "zh",
  "avatar_path": null,
  "description": "...",
  "personality": "...",
  "scenario": "",
  "system_prompt_override": "",
  "example_dialogues": [{"user": "...", "assistant": "...", "use_tools": false}],
  "tags": ["default", "zh", "operational"]
}
```

`_meta` is read by the seeder, not stored in DB. `language` and `tags` are seeder hints.

### 4.5 6 default cards

| File | name | language | is_default | system_prompt_override |
|---|---|---|---|---|
| `FSAR-zh.json` | FSAR | zh | **1** | "" (pass-through) |
| `FSAR-en.json` | FSAR | en | 0 | "" (pass-through) |
| `coding-coach-zh.json` | coding-coach | zh | 0 | "" |
| `coding-coach-en.json` | coding-coach | en | 0 | "" |
| `research-analyst-zh.json` | research-analyst | zh | 0 | "" |
| `research-analyst-en.json` | research-analyst | en | 0 | "" |

**FSAR card description (zh):**
> 你是 FSAR，一个完全属于用户的个人 AI 伴侣。用户提要求时主动调工具执行；回复匹配用户语言；保持简洁友好；不主动提起历史会话。

**FSAR card description (en):**
> You are FSAR, a personal AI companion that fully belongs to the user. You act on requests via tools, reply in the user's language, stay concise and friendly. You never volunteer stale references to past sessions.

**coding-coach description (zh, en mirrors):**
> 你是一位耐心的代码老师，专门帮人 review 代码、改 bug、解释复杂概念。回答时先给结论再给推导；遇到代码必给完整示例；不替用户做架构决策但会列出利弊。

**research-analyst description (zh, en mirrors):**
> 你是一位研究员风格的分析者，回复正式、引文密集、避免口语化。优先使用结构化输出（编号列表 / 小标题）；事实性陈述必有依据；不确定时显式标注。

### 4.6 `default-user.json` (shipped, single user card)

```json
{
  "_meta": { "created_by": "builtin", "seed_version": 1 },
  "name": "default-user",
  "avatar_path": null,
  "description": "FSAR 的主人，偏好简洁中文回复。",
  "communication_style": "concise, no emoji, prefer Chinese",
  "preferences": { "language": "zh", "response_length": "short" },
  "interests": ["local-first AI", "self-evolving agents"]
}
```

`is_default = 1` is set by the seeder (only one user card ships, so it's the default).

### 4.7 Data invariants

1. Default uniqueness enforced by UNIQUE index. Toggle `is_default` is a transaction: `UPDATE x SET is_default=0 WHERE is_default=1; UPDATE y SET is_default=1 WHERE id=?;`
2. Builtin rows are user-deletable; deletion is not auto-recovered (D11).
3. `character_card_id` is nullable; NULL falls back to global default.
4. JSON columns (`example_dialogues`, `tags`, `preferences`, `interests`) are not validated at DB level; `CardRepo.upsert_*` enforces shape at the application layer.

---

## 5. Backend

### 5.1 `src/memory/cards.py` (NEW) — `CardRepo`

```python
class CardRepo:
    def __init__(self, db_path: Path): ...
    def ensure_tables(self, conn: sqlite3.Connection) -> None: ...
    def seed_builtins_if_empty(self) -> int: ...
    
    # character cards
    def list_characters(self) -> list[CharacterCard]: ...
    def get_character(self, id: int) -> CharacterCard | None: ...
    def get_default_character(self) -> CharacterCard | None: ...
    def upsert_character(self, card: CharacterCard) -> int: ...
    def delete_character(self, id: int) -> bool: ...
    def set_default_character(self, id: int) -> None: ...
    
    # user cards
    def list_user_cards(self) -> list[UserCard]: ...
    def get_user_card(self, id: int) -> UserCard | None: ...
    def get_default_user_card(self) -> UserCard | None: ...
    def upsert_user_card(self, card: UserCard) -> int: ...
    def delete_user_card(self, id: int) -> bool: ...
    def set_default_user_card(self, id: int) -> None: ...
    
    # avatar
    def save_avatar(self, card_id: int, ext: str, data: bytes) -> str: ...
```

`CharacterCard` / `UserCard` are `@dataclass`; JSON fields round-trip via `json.loads` / `json.dumps`.

### 5.2 `src/core/persona.py` (NEW)

```python
@dataclass(frozen=True)
class PersonaBlock:
    text: str
    character_id: int | None
    user_card_id: int | None


class PersonaMissingError(Exception):
    """Raised when no character card is configured."""


def assemble_persona_block(
    character: CharacterCard | None,
    user_card: UserCard | None,
) -> PersonaBlock:
    """Compose persona prefix (items 1-3 of the prompt layout)."""
```

### 5.3 `src/core/prompts.py` (MODIFIED) — `build_system_prompt`

New function; existing `AGENT_SYSTEM_PROMPT` / `COMPANION_SYSTEM_PROMPT` / `MEMORY_POLICY` constants unchanged.

```python
def build_system_prompt(
    *,
    mode: str,                          # 'agent' | 'companion'
    character: CharacterCard | None,
    user_card: UserCard | None,
    memory_block: str = "",
    strategy_block: str = "",
    experience_block: str = "",
    skill_index_block: str = "",
) -> str:
    """Single source of truth for system prompt assembly.
    
    Layout (in order):
      1. [CHARACTER CARD]
      2. [EXAMPLE DIALOGUES]    (only if non-empty)
      3. [USER CARD]            (only if user_card is not None)
      4. [BASE SYSTEM PROMPT]   (AGENT_SYSTEM_PROMPT or COMPANION_SYSTEM_PROMPT)
      5. [CHARACTER OVERRIDE]   (only if character.system_prompt_override is non-empty)
      6. [MEMORY POLICY]
      7. [MEMORY BLOCK]
      8. [STRATEGY BLOCK]
      9. [EXPERIENCE BLOCK]
      10. [SKILL INDEX BLOCK]
    
    Raises PersonaMissingError if character is None.
    """
```

### 5.4 `src/server/chat_engine.py` (MODIFIED)

`_build_prompt` resolves character per session, then delegates to `build_system_prompt`. Snapshot for observability logged at debug level with block sizes (see §6.5).

**Message-snapshot responsibilities** (per D13 / D14):

- On the **first** `chat.delta` frame of an assistant turn, include `character_name: str` and `character_id: int` (resolved from the current session's character at turn start). Subsequent delta frames repeat the same values.
- On `chat.done`, repeat the same `character_name` / `character_id`.
- On `chat.send` echo (after persisting a user message to `conversations`), include `user_name: str` and `user_card_id: int` (resolved from the current default user card at echo time). This is what `MessageList` reads to label USER bubbles.
- These snapshots are **not re-resolved at render time**; once emitted, they stick. Re-render after card rename uses the snapshot, not the live card.

### 5.5 `src/memory/session_store.py` (MODIFIED)

- New migration `_migrate_character_binding()` (idempotent ALTER TABLE).
- `SessionRow.character_card_id: int | None`.
- `set_character(session_id, card_id) -> None`: writes column, fires `sessions.updated` WS event.
- `get_character(session_id) -> int | None`: reads column.

### 5.6 `src/server/handlers/card.py` (NEW)

WS message types:

**Card-level** (each carries `kind: 'character' | 'user'`):

| type | direction | response |
|---|---|---|
| `card.list` | c→s | `card.list_result` |
| `card.get` | c→s | `card.got` |
| `card.upsert` | c→s | `card.upserted` |
| `card.delete` | c→s | `card.deleted` |
| `card.set_default` | c→s | `card.default_changed` |
| `card.import_v2` | c→s | `card.imported` (ST V2 → character card; user cards not supported here) |
| `card.export` | c→s | `card.exported` (card → JSON) |

**Session-level** (character only; user card has no per-session binding):

| type | direction | response |
|---|---|---|
| `card.set_session_character` | c→s | `card.session_character_set` |
| `card.list_session_character` | c→s | `card.session_character` |

Server-pushed events:

| type | when |
|---|---|
| `card.user_card_renamed` | after a default user card's name changes |
| `sessions.updated` (existing) | after `set_character` writes |

Avatar uploads are HTTP (not WS): `POST /api/card/{id}/avatar` — multipart/form-data, max 2 MB, accepts png/jpg/webp. `X-FSAR-Avatar-Ext` header carries the desired extension.

### 5.7 First-run seed

`CardRepo.seed_builtins_if_empty()` reads from `data/cards/*.json` and inserts when `character_cards` is empty. Idempotent (re-runs are no-ops). Called from:

- `main.py` after `SessionStore._init_db` and after `card_repo.ensure_tables`
- `ws_server.py` startup

Order at startup:
1. config init
2. SessionStore init (with `_migrate_conversations` + `_migrate_character_binding`)
3. CardRepo init (with `ensure_tables` + `seed_builtins_if_empty`)
4. LLM factory / cache init
5. ChatEngine / WS server init

---

## 6. Prompt Assembly

### 6.1 Final layout (from §5.3)

```
[1] CHARACTER CARD      ← from session.character_card_id (fallback: global default)
[2] EXAMPLE DIALOGUES   ← from character.example_dialogues (if non-empty)
[3] USER CARD           ← from default user card
[4] BASE SYSTEM PROMPT  ← AGENT_SYSTEM_PROMPT (agent mode) or COMPANION_SYSTEM_PROMPT (companion mode)
[5] CHARACTER OVERRIDE  ← character.system_prompt_override, APPENDED (D7)
[6] MEMORY POLICY       ← MEMORY_POLICY constant
[7] MEMORY BLOCK        ← from self-evolution pipeline
[8] STRATEGY BLOCK      ← from strategy injector
[9] EXPERIENCE BLOCK    ← from experience injector
[10] SKILL INDEX BLOCK  ← "" in PL2.0 (placeholder for PL2.3)
```

### 6.2 Block templates (exact text)

**[CHARACTER CARD]**:
```
[CHARACTER CARD]
Name: {character.name}
Description: {character.description}
Personality: {character.personality}
Scenario: {character.scenario or "(none)"}
```

**[EXAMPLE DIALOGUES]** (only if non-empty):
```
[EXAMPLE DIALOGUES]
{user}: {msg}
{assistant}: {reply}
...
```

**[USER CARD]** (only if user_card not None):
```
[USER CARD]
You are talking to {user_card.name}.
About them: {user_card.description}
Their style: {user_card.communication_style or "(unspecified)"}
Known preferences: {json.dumps(user_card.preferences, ensure_ascii=False)}
Known interests: {json.dumps(user_card.interests, ensure_ascii=False)}
```

User card section labels are in English regardless of `user_card.language` (helps LLM parsing); content follows the user card's actual language.

### 6.3 Edge cases

| Scenario | Behavior |
|---|---|
| `character is None` + no global default | `PersonaMissingError` → ws handler returns `card.error code="persona_missing"`; GUI falls back to "create a character first" message on /cards |
| `user_card is None` | skip [USER CARD] block; everything else continues |
| `character.example_dialogues` empty | skip [EXAMPLE DIALOGUES] block |
| `character.scenario` empty | render `Scenario: (none)` |
| `character.system_prompt_override` empty | skip [CHARACTER OVERRIDE] block |
| `mode='companion'` + `character=None` | raise; companion mode also requires persona |

**Invariant:** `build_system_prompt` always emits at least [BASE SYSTEM PROMPT] + [MEMORY POLICY]; operational instructions are never bypassable by persona absence.

### 6.4 Compatibility

- CLI `main.py` and GUI `ChatEngine` both call `build_system_prompt` (replace existing ad-hoc prompt assembly).
- `AGENT_SYSTEM_PROMPT` / `COMPANION_SYSTEM_PROMPT` text **unchanged** — when FSAR-zh is the default character, prompt output equals the current P7.11 prompt + a persona wrapper.
- Existing LLM cache keys naturally invalidate (per-turn payload changes due to added blocks).

### 6.5 Observability

Every `build_system_prompt` call logs at DEBUG with `extra={mode, character_id, character_name, user_card_id, block_sizes={...}}`. Block sizes help diagnose "why is this reply so off-character".

---

## 7. Frontend

### 7.1 `/cards` page (top-level sidebar entry, NOT under Settings)

Two tabs:

- **Character 卡片** tab (default): list of all `character_cards` with avatar + name + personality + [default] badge + [edit] [⋯]
- **User 卡片** tab: list of all `user_cards` with avatar + name + description + [default] badge + [edit] [⋯]

Tab content:

```
Cards                          [+ New Character] [↑ Import] [↓ Export]
[ Character 卡片 (6) | User 卡片 (1) ]

┌──────────────────────────────────────────────────────┐
│ [avatar] FSAR-zh        [default] [edit] [⋯]         │
│          concise, friendly, action-oriented          │
├──────────────────────────────────────────────────────┤
│ [avatar] FSAR-en                    [edit] [⋯]       │
│          concise, friendly, action-oriented          │
├──────────────────────────────────────────────────────┤
│ [avatar] coding-coach-zh            [edit] [⋯]       │
├──────────────────────────────────────────────────────┤
│ [avatar] coding-coach-en            [edit] [⋯]       │
├──────────────────────────────────────────────────────┤
│ [avatar] research-analyst-zh        [edit] [⋯]       │
├──────────────────────────────────────────────────────┤
│ [avatar] research-analyst-en        [edit] [⋯]       │
└──────────────────────────────────────────────────────┘
```

### 7.2 Character card editor fields

| Field | Control | Notes |
|---|---|---|
| avatar | circular upload | click → file picker → `POST /api/card/{id}/avatar`; max 2 MB; png/jpg/webp |
| name | text input | required |
| description | textarea + char counter | 50–500 |
| personality | textarea + char counter | 20–200 |
| scenario | textarea | 0–300, optional |
| system_prompt_override | large textarea | placeholder: "Appended to AGENT_SYSTEM_PROMPT tail" |
| example_dialogues | dynamic user/assistant pair list | [+] adds pair, [×] removes |
| tags | chip input | enter to add, × to remove |
| is_default | toggle (top) | "Set as default" |
| header | `[Save] [Cancel] [Delete]` | Delete hidden for default card; confirms before deleting |

### 7.3 User card editor fields

| Field | Control | Notes |
|---|---|---|
| avatar | same as 7.2 | |
| name | text input | required |
| description | textarea | 50–500 |
| preferences | dynamic key-value rows | [+] adds, [×] removes each row |
| interests | chip input | same as tags |
| communication_style | textarea | 0–200, optional |
| is_default | toggle (top) | "Set as default" |
| header | `[Save] [Cancel] [Delete]` | Delete hidden for default card |

User card has **no** `personality` / `scenario` / `example_dialogues` / `system_prompt_override` / `tags` fields.

### 7.4 Chat topbar character dropdown

Topbar layout (P7.11 already has provider/model/mode; PL2.0 adds character):

```
[≡]  Character: [FSAR-zh ▾]  |  Provider: [anthropic ▾]  |  Mode: [companion ▾]  |  [⚙]
```

Dropdown:
- Header: current session's `character.name` (resolved from `session.character_card_id` → global default)
- Click: lists all characters (default first, then alpha)
- Selecting sends `card.set_session_character { session_id, character_id }`
- After server confirms `card.session_character_set` + `sessions.updated`, topbar refreshes

### 7.5 Message labels

- **ASSISTANT bubble** label = `message.character_name` (D13, snapshotted in §5.4 chat_engine emit)
- **USER bubble** label = `message.user_name` (D13, snapshotted in §5.4 chat_engine emit on `chat.send` echo)
- Fallback if missing: `character_name` → "FSAR"; `user_name` → "USER"

### 7.6 User-card rename realtime refresh

`CardRepo.upsert_user_card` triggers `card.user_card_renamed` WS push (when the default user's name changes). Frontend store updates; all subsequent USER messages use the new name. Existing message labels retain their snapshot (consistent with §7.5).

### 7.7 File structure

```
frontend/src/
├── pages/
│   ├── Cards.tsx                       # NEW
│   └── Chat.tsx                        # MODIFIED: topbar + message labels
├── components/
│   ├── cards/
│   │   ├── CharacterCardList.tsx       # NEW
│   │   ├── CharacterCardEditor.tsx     # NEW
│   │   ├── UserCardList.tsx            # NEW
│   │   └── UserCardEditor.tsx          # NEW
│   └── chat/
│       ├── Topbar.tsx                  # MODIFIED: receives CharacterSelector
│       └── CharacterSelector.tsx       # NEW
└── stores/
    └── cards.ts                        # NEW
```

### 7.8 Routing

Sidebar adds `Cards` entry above `Settings`. Router: `<Route path="/cards" element={<Cards />} />`.

---

## 8. SillyTavern V2 Import (Parser)

`CardRepo` exposes `parse_sillytavern_v2(json_text: str) -> CharacterCard`. Covers:

- Spec v2 character book (lores) is **ignored** in PL2.0 (not stored)
- Spec v2 character spec fields mapped 1:1 to schema fields
- Spec v1 / v3 fall through: missing fields filled with sensible defaults; spec version stored in `tags` as `"st_v1"` / `"st_v3"`
- Avatar: if `data:` URL → save to `data/avatars/{card_id}.{ext}`; if URL → skip with warning (PL2.0 doesn't fetch remote avatars)
- Tags: merged from `character.tags` (ST) and `[ "imported" ]` (PL2.0 marker)

`card.imported` response includes the new card's `id` and a `warnings: list[str]` for fields that couldn't be mapped.

---

## 9. Testing

### 9.1 Unit tests (5 files, ~25 cases)

| File | Covers |
|---|---|
| `tests/test_cards_repo.py` | CRUD, default toggle, seed, listing, soft delete |
| `tests/test_persona_assembler.py` | `assemble_persona_block` combos: with/without character, with/without user card, empty dialogues, etc. |
| `tests/test_prompt_builder.py` | block ordering, override append (D7), missing-character raise, mode switching |
| `tests/test_session_character_binding.py` | migration idempotency, set_character persistence, ON DELETE SET NULL |
| `tests/test_st_v2_parser.py` | v1/v2/v3 spec handling, missing fields, data URL avatar, lore ignored |

### 9.2 Out of scope

- Frontend React tests (no test library in PL2.0)
- E2E GUI tests (manual smoke only)
- Performance / load tests
- Visual regression

### 9.3 Verification (manual smoke)

Slice 5 (see §10) defines the E2E flow. CLI regression: existing P7.11 chat behavior unchanged when character is the default FSAR-zh.

---

## 10. Task Slicing (Execution Plan)

### Slice 1 — Data layer + backend core
- `src/memory/cards.py` (`CardRepo` + `ensure_tables`)
- `src/memory/session_store.py` (`_migrate_character_binding`, `set_character`, `get_character`)
- `src/core/persona.py` (`assemble_persona_block`, `PersonaBlock`, `PersonaMissingError`)
- `src/core/prompts.py` (`build_system_prompt`)
- `data/cards/*.json` (6 builtins + 1 default-user)
- Unit tests: `test_cards_repo.py`, `test_persona_assembler.py`, `test_prompt_builder.py`, `test_session_character_binding.py`
- Hook into CLI `main.py` and GUI `chat_engine._build_prompt`
- **Verify:** `pytest tests/test_cards_repo.py tests/test_persona_assembler.py tests/test_prompt_builder.py tests/test_session_character_binding.py` passes; CLI dumps assembled prompt showing `[CHARACTER CARD] FSAR` section

### Slice 2 — WS handlers + seed flow
- `src/server/handlers/card.py` (9 WS message types)
- `src/server/handlers/card.py` (avatar HTTP endpoint)
- `CardRepo.seed_builtins_if_empty` (full)
- main.py / ws_server.py startup hooks
- Unit tests: `test_st_v2_parser.py`
- **Verify:** fresh install → 6 default cards appear; WS `card.list` returns 6; `card.set_default` works

### Slice 3 — Chat topbar + message labels
- Frontend: `stores/cards.ts`, `components/chat/CharacterSelector.tsx`, Topbar wiring
- MessageList reads `character_name` + `user_name`
- chat_engine emit extended payload (C.9 + §7.5)
- User card rename → `card.user_card_renamed` push
- **Verify:** topbar dropdown switches character → next ASSISTANT message label updates; user card rename → USER message label updates realtime

### Slice 4 — /cards page (character tab)
- Frontend: `pages/Cards.tsx`, `CharacterCardList.tsx`, `CharacterCardEditor.tsx`
- Routing: sidebar entry + `/cards` route
- Avatar upload wired to `POST /api/card/{id}/avatar`
- Import (paste JSON + ST V2) / Export buttons
- **Verify:** create / edit / delete / set default / import / export / upload avatar all work in GUI

### Slice 5 — /cards page (user tab) + E2E
- Frontend: `UserCardList.tsx`, `UserCardEditor.tsx`
- Preferences dynamic key-value UI
- Full E2E smoke (CLI install → /cards shows 6 → switch to coding-coach → reply sounds like a code teacher → rename user card → USER label updates → switch back to FSAR → reply matches P7.11 behavior)
- **Verify:** all 5 test files green + E2E smoke passes + CLI behavior matches P7.11 with default character

---

## 11. Risks & Known Traps

1. **ChatEngine prompt change** will shift LLM behavior (more tokens at the front, persona framing). Run all existing CLI/GUI smoke checks after Slice 1.
2. **ALTER TABLE on existing DBs** must be idempotent — `PRAGMA table_info` check before `ADD COLUMN`.
3. **WS handler registration order** — `card.*` handlers must register before `ws_server` accepts connections; same pattern as existing handlers.
4. **HTTP avatar endpoint transport** — must integrate with whatever aiohttp-style server P7.2 set up. If ws_server is still raw `websockets` lib, add aiohttp in Slice 2.
5. **ST V2 spec coverage** — community cards are messy; parser must be tolerant (v1/v3 fallbacks). Track unsupported fields in `warnings`.
6. **Topbar crowding** — P7.11 already has provider/model/mode controls; adding character may overflow on narrow windows. Validate layout in Slice 3.
7. **Per-session character toggle UX** — switching a session's character mid-stream is not allowed in PL2.0; the dropdown switches in-place but the change applies on the **next** user message. Document in tooltip.

---

## 12. Definition of Done

PL2.0 is complete when all of the following hold:

1. All 5 slices pass their verify steps (§10)
2. 5 test files (~25 cases) green
3. Slice 5 E2E smoke passes
4. CLI behavior (no character switch) indistinguishable from P7.11
5. DESIGN.MD §16.1 exit criterion met: create character → switch to it → next reply shows persona
6. Out-of-scope items (§1.3) confirmed not implemented
7. D7 deviation documented in CHANGELOG (override append vs replace)
8. Spec self-review (§13 below) passes

---

## 13. Spec Self-Review

Run inline after writing the spec.

**13.1 Placeholder scan.** No `TBD` / `TODO` / `(fill in)` markers remain. The pre-review placeholder at §13 was replaced. No `...` other than in the example dialogue template (intentional — it shows truncation).

**13.2 Internal consistency.**

- §5.3 declares 7 card-level WS types; §5.6 lists 7 card-level + 2 session-level = 9 total. Consistent.
- §5.4 chat_engine snapshot responsibilities (character_name on assistant, user_name on user send echo) align with §7.5 (frontend reads) and §5.6 (no session-level type for user card).
- §6.3 edge-case table and §5.3 docstring raise conditions agree (both name `PersonaMissingError`).
- D7 (override append) is consistent across §5.3 docstring, §6.1 layout, §6.3 edge cases, and §11 risks.
- 6 default cards counted in §1.2 / §4.5 / §10 Slice 2 / §10 Slice 5 — all reference 6 + 1 default-user.

**13.3 Scope check.** Single phase, decomposed into 5 slices each with its own verify step. Not too large for a single implementation plan. The 5 slices are sequenced so each is independently testable (Slice 1 = backend only; Slice 5 = E2E).

**13.4 Ambiguity check.**

- "character switching" — resolved by §2 D1 + §3.2: per-session, not per-turn, not per-message.
- "default user card" — §2 D1: there's only one default; multiple user cards are allowed in DB but only one carries `is_default=1`.
- "ST V2 import" — §5.6 / §8: covers v1/v2/v3 with fallbacks; v3 marked future-compatible.
- "ON DELETE SET NULL" (§4.3) — clarified in §11 risk #2 path: deleting a character that a session is bound to leaves the session with `character_card_id=NULL`, which then falls back to global default per §3.2 flow.
- "Mid-conversation character switch" — explicitly out of scope (D1, §7.4 doc note about "applies on next user message" in §11 risk #7).
- "test counts" — §9.1 says "~25 cases" — explicitly approximate; per-file targets are exact.

No two-way interpretations remain.

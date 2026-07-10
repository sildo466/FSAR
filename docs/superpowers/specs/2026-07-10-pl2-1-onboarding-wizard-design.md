# PL2.1 — Onboarding Wizard

**Date:** 2026-07-10
**Status:** Design (awaiting user review)
**Phase:** PL2.1 (per DESIGN.MD §16.2)
**Scope:** First-run detection, 3-step wizard (provider → user card → character card), 25 built-in LLM provider presets, test connection, model list fetching, SillyTavern V2 PNG import, persistence via `fsar.yaml` + `data/memory.db`

---

## 1. Purpose & Exit Criteria

### 1.1 Purpose

Bridge the gap between "just installed FSAR" and "can have a personalized conversation with a character driven by my LLM". PL2.0 ships 6 default character cards and 1 default user card, but a fresh install has no LLM configured — the user must add an API key, pick a model, and identify themselves before chat is usable. PL2.1 packages that one-time setup as a guided flow.

### 1.2 Exit Criteria (from DESIGN.MD §16.2, refined)

> Clean install → wizard appears automatically → user completes 3 steps → lands in `/chat` → can send a message to default character → reply is generated via the configured LLM → wizard does not reappear on next launch → `Settings → Advanced → Reset Onboarding` correctly re-triggers it.

### 1.3 Explicit non-goals (PL2.1 does NOT do)

| Item | Reason | Phase |
|---|---|---|
| Wire LLM `chat.send` to a new family-specific code path (uses hermes-agent reference) | Out of wizard scope; ChatEngine already wired in P7.11 | PL2.5+ |
| Google Gemini live protocol | preset flagged `deferred: true`; UI greys it out | PL2.5 |
| Workspace / sandbox (per-conversation file gates) | DESIGN.MD §16.3 | PL2.2 |
| Avatar guided circular crop + zoom + rotate (mirror SillyTavern) | Wizard ships square crop only; full crop UX deferred until D-D10 reference review | PL2.7 |
| Marketplace / community sharing of cards / Intergrations | DESIGN.MD §19 Q6 | PL3+ |
| Per-conversation user card override (PL2.0 D4) | Global default only | PL3+ |
| LLM call request body / headers per family (use hermes-agent reference) | Out of wizard scope | PL2.5+ |
| Provider family auto-detection from base_url | User picks preset explicitly; no sniffing | PL3+ |

---

## 2. Decisions (locked)

Decisions made through brainstorming (2026-07-10). Numbered for spec cross-reference.

### 2.1 Scope & reuse

| # | Decision | Deviates from DESIGN.MD? |
|---|---|---|
| A-D1 | Wizard reuses P7.8's `FsarConfig.add_provider()` and `Settings → Models` provider schema; no parallel data path | Slight: doc describes independent provider CRUD; we share with P7.8 |
| A-D2 | 25 built-in preset vendors (not 7 as in DESIGN.MD §6.1) | Yes — 7 was a doc-era number; user asked to expand to ≥20 with MiniMax Global and 5 international relays; final 25 |
| A-D3 | `data/presets/llm-providers.json` is the single source of vendor metadata; Python loads + validates at startup | New (DESIGN.MD has `BUILTIN_PRESETS` Python constant; we move to JSON for editability) |
| A-D4 | Provider step is **enforced for completion of wizard**; other two steps can be skipped (use defaults) | Yes — DESIGN.MD §4.2 says "at minimum step 1 (provider) is enforced"; we keep that |

### 2.2 Models (B-D)

| # | Decision |
|---|---|
| B-D1 | Presets never contain any hardcoded model string. Models always come from (a) `GET {base_url}/models` (openai_compat with `model_list_url_suffix` set) or (b) user-typed free text |
| B-D2 | `model_list_url_suffix: null` in preset → wizard's [Load model list] button is disabled with tooltip "This provider has no model list API" (Anthropic, Google) |
| B-D3 | `test_url_suffix: null` (Anthropic) → test uses POST `/v1/messages` with `{"model": <user-typed>, "max_tokens": 1, "messages": [{"role": "user", "content": "hi"}]}`; 200/400 = ok; 401 = auth_failed; if model empty → `error: "model_required"` |
| B-D4 | `fsar.yaml.llm.providers[].model` is required (cannot be empty) but is **never** preset-provided; user always selects or types it |
| B-D5 | `fsar.yaml.llm.providers[].family` is locked to the preset's family (not editable in UI); prevents openai_compat → Anthropic endpoint misuse |
| B-D6 | `${ENV_VAR}` placeholder in `api_key` field is supported (P7.1 Task 4 already in FsarConfig) |
| B-D7 | **First-run detection**: on `ws_server.start()` → check if `config/fsar.yaml` exists → if not, copy from `config/fsar.yaml.template` (which contains `onboarding: { completed: false, completed_steps: [] }` and empty `llm.providers: []`); set `onboarding.required = true` for the resulting snapshot |
| B-D8 | `onboarding.required` in WS snapshot = `not fsar.yaml.onboarding.completed`; computed at snapshot time, not stored |
| B-D9 | `onboarding.completed` only true after all 3 steps complete (`provider` + `user_card` + `character_card`); any skip on `character_card` still marks the step as done (with `mode: "skipped"`) |
| B-D10 | `family` valid values: `openai_compat` / `anthropic` / `google`; `deferred: true` presets surface in wizard with greyed card + tooltip "Available in a future phase" |
| B-D11 | Each step's `complete_step` writes `fsar.yaml` atomically (FsarConfig.save already provides this) |
| B-D12 | `test_connection` timeout = 5s; classified errors: `unreachable` / `auth_failed` / `bad_request` / `model_required` / `deferred` / `unknown` |
| B-D13 | LLM chat call request bodies/headers per family reference `D:/hermes/hermes-agent`; out of scope for PL2.1 (wizard only does GET `/models` and minimal POST probes) |

### 2.3 WS protocol (C-D)

| # | Decision |
|---|---|
| C-D1 | `provider.test_connection` uses user-typed model for probing; if empty → `error: "model_required"` |
| C-D2 | `test_connection` classifies as `unreachable` / `auth_failed` / `bad_request` / `model_required` / `deferred` / `unknown` based on HTTP status / exception type |
| C-D3 | `provider.fetch_models` does GET `{base_url}{model_list_url_suffix}`; no model arg needed; 5s timeout; returns `models: [id, ...]` |
| C-D4 | `provider.create_builtin.preset_id` is required; `family` is server-derived from preset (client cannot override) |
| C-D5 | `onboarding.complete_step` writes `completed_steps` incrementally; never reverts |
| C-D6 | `onboarding.complete` only fires when `completed_steps == ["provider", "user_card", "character_card"]`; on success writes `onboarding.completed: true` and pushes `onboarding.completed` with `redirect: "/chat"` |
| C-D7 | `onboarding.reset` writes `onboarding.completed: false` + clears `completed_steps`; client can re-mount wizard |
| C-D8 | `provider.test_connection` does not cache results; user re-tests after any base_url / api_key change |
| C-D9 | Google Gemini `test_connection` returns `ok: false, error: "deferred"` without making any HTTP call |

### 2.4 Frontend (D-D)

| # | Decision |
|---|---|
| D-D1 | Provider step [Next] is **not strictly blocked** by failed test; failed test shows warning banner "Test failed — continue anyway?" and button text becomes [Continue anyway]. User can still save. (R2 mitigation) |
| D-D2 | User card step updates the existing `default-user` (PL2.0 seed) via `card.upsert(kind="user", ...)`; never creates a second user card in the wizard |
| D-D3 | Character card step has 4 mutually exclusive modes: `use_default` (calls `card.set_default(kind="character", id=FSAR-zh.id)`) / `pick_existing` (selects from PL2.0 seed 6 + any user-created) / `create_new` (form + `card.upsert + set_default`) / `import_st` (PNG tEXt parser + upsert) |
| D-D4 | "Create new" avatar upload is a square 1:1 crop only (no rotation, no zoom-to-circle); full circular crop UX mirrors SillyTavern is deferred (D-D10 reference) |
| D-D5 | "Import ST image" uses PL2.0's existing `StV2Parser` to read PNG tEXt chunks; failure shows error toast but does not block wizard progress (D-D9) |
| D-D6 | "Pick existing" lists all 6 PL2.0 default character cards (FSAR-zh/en, coding-coach-zh/en, research-analyst-zh/en) plus any user-created; clicking one calls `set_default` |
| D-D7 | Wizard does not cache local-only state across sessions; on remount it reads `fsar.yaml.completed_steps` to position the user at the next unfinished step |
| D-D8 | On `onboarding.completed` event, `useWizardState` triggers `router.push("/chat")` |
| D-D9 | ST PNG import failure: error toast, wizard continues with previous character_card state unchanged |
| D-D10 | Avatar crop UX scope (full circular + zoom + rotate) is referenced against `C:\WinTool\SillyTavern\SillyTavern`; PL2.1 ships square only; full feature may land in PL2.7 |

### 2.5 Process (E-D)

| # | Decision |
|---|---|
| E-D1 | Test suite minimum: 21 backend tests + 10 frontend tests; all must pass before PL2.1 closes |
| E-D2 | `config/fsar.yaml` and `config/fsar.yaml.bak` added to `.gitignore`; `config/fsar.yaml.template` remains tracked as the bootstrap template |
| E-D3 | Manual E2E with a real OpenAI or Anthropic key is required before PL2.1 closes (no LLM call yet, but wizard + test connection + provider create + chat handoff must be verified) |

---

## 3. Architecture

### 3.1 Component diagram

```
┌────────────────────────────────────────────────────────────┐
│  Frontend (React)                                          │
│                                                             │
│  /onboarding (full-screen overlay; mounted when            │
│              snapshot.onboarding.required = true)           │
│  ┌──────────────────────────────────────────────────┐      │
│  │ WizardShell (progress indicator: 3 dots)          │      │
│  ├──────────────────────────────────────────────────┤      │
│  │ Step 1 · Provider                                  │      │
│  │  PresetGrid (25 cards, 4 columns)                 │      │
│  │  PresetDetailPanel (right side, 320px slide-in)   │      │
│  │    - ApiKeyField                                   │      │
│  │    - BaseUrlField (label "Fill to /v1")            │      │
│  │    - ModelField ([Load list] + text input)         │      │
│  │    - TestConnectionButton                          │      │
│  │  StepFooter: [Back ◀] [Next ▶]                    │      │
│  ├──────────────────────────────────────────────────┤      │
│  │ Step 2 · User Card                                 │      │
│  │  UserNameField                                     │      │
│  │  UserBioTextarea                                   │      │
│  │  StepFooter: [Back ◀] [Next ▶]                    │      │
│  ├──────────────────────────────────────────────────┤      │
│  │ Step 3 · Character Card (skippable)                │      │
│  │  4-option segmented:                               │      │
│  │    [Use default] [Pick existing] [Create new]      │      │
│  │    [Import ST image]                               │      │
│  │  StepFooter: [Back ◀] [Skip] [Finish ▶]           │      │
│  └──────────────────────────────────────────────────┘      │
└────────────────────────┬───────────────────────────────────┘
                         │ WS (JSON protocol §4)
┌────────────────────────▼───────────────────────────────────┐
│  Backend                                                    │
│  src/server/handlers/                                       │
│    onboarding.py        # get_state / complete_step /       │
│                         # complete / reset                  │
│    provider.py          # list_presets / create_builtin /   │
│                         # test_connection / fetch_models    │
│  src/providers/llm/                                       │
│    presets.py           # load + validate 25 presets        │
│  data/presets/                                            │
│    llm-providers.json   # vendor metadata                   │
│  src/utils/fsar_config.py   # add_provider (reuse)          │
│  src/memory/cards.py        # card CRUD (reuse)             │
│  config/fsar.yaml.template  # bootstrap template            │
└────────────────────────┬───────────────────────────────────┘
                         │
                ┌────────▼─────────┐
                │ config/fsar.yaml │ ← onboarding state + providers
                │ data/memory.db   │ ← user_cards + character_cards
                │ data/avatars/    │ ← uploaded avatar files
                └──────────────────┘
```

### 3.2 Data flow

```
User launches FSAR (clean install)
  → main.py starts ws_server
  → ws_server detects config/fsar.yaml missing
  → copies config/fsar.yaml.template → config/fsar.yaml
  → loads presets from data/presets/llm-providers.json (25)
  → loads FsarConfig → onboarding.completed = false
  → snapshot sent to client includes onboarding.required = true

Client receives snapshot
  → useWS sees onboarding.required = true
  → /onboarding route mounted (full-screen overlay)
  → useWizardState.step = "provider"
  → fetches 25 presets via provider.list_presets

User completes Step 1 (provider)
  → POST provider.create_builtin (preset_id, api_key, base_url, model)
  → Server: FsarConfig.add_provider (writes fsar.yaml atomically)
  → POST onboarding.complete_step("provider")
  → Server: appends "provider" to completed_steps
  → useWizardState.step = "user_card"

User completes Step 2 (user card)
  → POST card.upsert(kind="user", card={name, bio})
  → POST onboarding.complete_step("user_card")
  → useWizardState.step = "character_card"

User completes Step 3 (character card, mode = use_default)
  → POST card.set_default(kind="character", id=FSAR-zh.id)
  → POST onboarding.complete_step("character_card", {mode: "skipped"})
  → useWizardState.step = "submitting"
  → POST onboarding.complete
  → Server: writes onboarding.completed = true + onboarding.completed_at
  → Server pushes onboarding.completed event with redirect: "/chat"
  → Client router.push("/chat")
  → /onboarding unmounts
```

### 3.3 Trigger conditions

| Condition | Result |
|---|---|
| `config/fsar.yaml` missing | Copy template → `onboarding.required = true` |
| `config/fsar.yaml` exists, `onboarding.completed != true` | `onboarding.required = true` |
| `config/fsar.yaml` exists, `onboarding.completed == true` | `onboarding.required = false` |
| User clicks `Settings → Advanced → Reset Onboarding` | `onboarding.completed = false`, restart → wizard re-appears |

---

## 4. Data Model

### 4.1 `data/presets/llm-providers.json` schema

```jsonc
[
  {
    "id": "openai",                              // string, unique, kebab/snake
    "label": "OpenAI",                           // string, English
    "label_localized": { "zh": "OpenAI", "en": "OpenAI" },   // optional
    "family": "openai_compat",                   // openai_compat | anthropic | google
    "default_base_url": "https://api.openai.com/v1",
    "default_headers": {},                       // object, e.g. {"anthropic-version": "..."}
    "api_key_required": true,
    "api_key_env": "OPENAI_API_KEY",             // optional: hint for env var name
    "model_list_url_suffix": "/models",          // string | null
    "test_url_suffix": "/models",                // string | null (null → POST messages probe)
    "deferred": false,                           // true → UI greys this card
    "icon": "openai",                            // string for frontend icon mapping
    "homepage": "https://platform.openai.com",
    "order": 1                                   // int, lower = first in grid
  }
  // ... 24 more entries
]
```

**Family taxonomy:**

| Family | Providers | Protocol endpoint | Test strategy |
|---|---|---|---|
| `openai_compat` | openai, deepseek, zhipu, qwen, moonshot, minimax, minimax-global, n1n, aihubmix, 302-ai, together, fireworks, volcengine, mimo, cerebras, cloudflare, nvidia, groq, mistral, openrouter, ollama, lmstudio | `{base_url}/chat/completions` | GET `{base_url}/models` |
| `anthropic` | anthropic | `{base_url}/messages` | POST `{base_url}/messages` with `max_tokens: 1` |
| `google` | google | (deferred) | (deferred) |

### 4.2 25 built-in vendors (locked)

| # | ID | Vendor | Base URL | Family |
|---|----|--------|----------|--------|
| 1 | openai | OpenAI | api.openai.com/v1 | openai_compat |
| 2 | anthropic | Anthropic | api.anthropic.com/v1 | anthropic |
| 3 | google | Google Gemini | generativelanguage.googleapis.com/v1beta | google (deferred) |
| 4 | xai | X.AI (Grok) | api.x.ai/v1 | openai_compat |
| 5 | groq | Groq | api.groq.com/openai/v1 | openai_compat |
| 6 | mistral | Mistral AI | api.mistral.ai/v1 | openai_compat |
| 7 | openrouter | OpenRouter | openrouter.ai/api/v1 | openai_compat |
| 8 | ollama | Ollama | localhost:11434/v1 | openai_compat |
| 9 | lmstudio | LM Studio | localhost:1234/v1 | openai_compat |
| 10 | deepseek | DeepSeek | api.deepseek.com/v1 | openai_compat |
| 11 | zhipu | Zhipu / Z.ai | open.bigmodel.cn/api/paas/v4 | openai_compat |
| 12 | qwen | Qwen / DashScope | dashscope.aliyuncs.com/compatible-mode/v1 | openai_compat |
| 13 | moonshot | Moonshot / Kimi | api.moonshot.cn/v1 | openai_compat |
| 14 | minimax | MiniMax (China) | api.minimaxi.com/v1 | openai_compat |
| 15 | minimax-global | MiniMax (Global) | api.minimax.io/v1 | openai_compat |
| 16 | n1n | N1N | api.n1n.ai/v1 | openai_compat |
| 17 | aihubmix | Aihubmix | aihubmix.com/v1 | openai_compat |
| 18 | 302-ai | 302.AI | api.302.ai/v1 | openai_compat |
| 19 | together | Together AI | api.together.xyz/v1 | openai_compat |
| 20 | fireworks | Fireworks AI | api.fireworks.ai/inference/v1 | openai_compat |
| 21 | volcengine | Volcengine / Doubao | ark.cn-beijing.volces.com/api/v3 | openai_compat |
| 22 | mimo | Xiaomi MiMo | api.xiaomimimo.com/v1 | openai_compat |
| 23 | cerebras | Cerebras AI | api.cerebras.ai/v1 | openai_compat |
| 24 | cloudflare | Cloudflare Workers AI | api.cloudflare.com/client/v4/accounts/{id}/ai/v1 | openai_compat |
| 25 | nvidia | NVIDIA NIM | integrate.api.nvidia.com/v1 | openai_compat |

### 4.3 `config/fsar.yaml` schema (wizard-relevant sections)

```yaml
onboarding:
  required: true                     # computed at snapshot time, not stored
  completed: false
  completed_at: null
  completed_steps: []                # ['provider', 'user_card', 'character_card']
  started_at: "2026-07-10T12:00:00Z"
  last_step: null                    # 'provider' | 'user_card' | 'character_card'

llm:
  active: "openai-1"                 # FsarConfig auto-suffixes with -N
  providers:
    - id: "openai-1"
      preset_id: "openai"            # reference to data/presets/llm-providers.json
      label: "OpenAI (primary)"
      base_url: "https://api.openai.com/v1"
      api_key: "${OPENAI_API_KEY}"   # ${ENV} expansion (P7.1 Task 4)
      model: "gpt-4o-mini"           # user-typed or fetched; never preset-provided
      family: "openai_compat"        # locked from preset
      enabled: true
      pricing:
        input_per_1k: 0.15
        output_per_1k: 0.60
      created_at: "2026-07-10T12:00:00Z"
      updated_at: "2026-07-10T12:00:00Z"

memory:
  default_user_card_id: 1            # set by Step 2 (PL2.0 seed default-user)
  default_character_card_id: 6       # set by Step 3 (FSAR-zh by default)
```

### 4.4 `data/avatars/` storage

- New uploads from wizard: `data/avatars/{uuid}.{ext}` (PNG/JPG/WebP, max 2MB)
- Existing PL2.0 D6: `data/avatars/{card_id}.{ext}` — wizard reuses same dir but uses UUID naming to avoid collision when re-uploading

---

## 5. WS Protocol

### 5.1 New client → server messages

```jsonc
{ "type": "onboarding.get_state" }
{ "type": "provider.list_presets" }
{ "type": "provider.create_builtin",
  "preset_id": "openai",
  "label": "OpenAI (primary)",
  "api_key": "${OPENAI_API_KEY}",
  "base_url": "https://api.openai.com/v1",
  "model": "gpt-4o-mini" }
{ "type": "provider.test_connection",
  "preset_id": "openai",              // for family lookup
  "base_url": "https://api.openai.com/v1",
  "api_key": "sk-...",
  "model": "gpt-4o-mini" }           // required for anthropic; optional for openai_compat
{ "type": "provider.fetch_models",
  "preset_id": "openai",
  "base_url": "https://api.openai.com/v1",
  "api_key": "sk-..." }
{ "type": "onboarding.complete_step",
  "step": "provider" | "user_card" | "character_card",
  "data": { /* step-specific */ } }
{ "type": "onboarding.complete" }
{ "type": "onboarding.reset" }
```

### 5.2 New server → client messages

```jsonc
{ "type": "onboarding.state",
  "required": true,
  "completed": false,
  "completed_steps": ["provider"],
  "current_step": "user_card" }
{ "type": "provider.presets",
  "presets": [PresetRow, ...] }       // 25 entries
{ "type": "provider.created",
  "provider": { "id": "openai-1", "preset_id": "openai", ... } }
{ "type": "provider.test_result",
  "ok": true,
  "error": null,                      // "unreachable" | "auth_failed" | "bad_request" | "model_required" | "deferred" | "unknown"
  "latency_ms": 234 }
{ "type": "provider.models",
  "ok": true,
  "models": ["gpt-4o-mini", "gpt-4o", ...],
  "error": null }
{ "type": "onboarding.step_completed",
  "step": "user_card" }
{ "type": "onboarding.completed",
  "redirect": "/chat" }
{ "type": "onboarding.error",
  "step": "character_card",
  "code": "avatar_too_large",
  "message": "Avatar must be ≤ 2MB" }
```

### 5.3 Modified messages

```jsonc
// snapshot (existing in P7.2) — adds onboarding field
{ "type": "snapshot",
  "config": { ... },
  "onboarding": {
    "required": true,
    "completed": false,
    "completed_steps": [],
    "current_step": "provider" } }
```

### 5.4 Error classification (test_connection)

| HTTP / Exception | Classification |
|---|---|
| 200 (openai_compat) | ok |
| 200 / 400 (anthropic with user model) | ok |
| 401 / 403 | auth_failed |
| 404 / 405 (anthropic) | bad_request (likely key passed but endpoint wrong) |
| Timeout / ConnectionError | unreachable |
| model empty (anthropic) | model_required |
| family = "google" | deferred |
| Other status code | unknown |

---

## 6. Frontend Architecture

### 6.1 Component tree

```
frontend/src/
├── pages/
│   └── Onboarding.tsx                          # /onboarding route, full-screen overlay
├── components/onboarding/
│   ├── WizardShell.tsx                         # progress indicator + container
│   ├── StepProvider.tsx
│   │   ├── PresetGrid.tsx                      # 25 cards, 4 columns
│   │   ├── PresetCard.tsx                      # single card (icon + label + description)
│   │   ├── PresetDetailPanel.tsx               # right slide-in (320px)
│   │   │   ├── ApiKeyField.tsx
│   │   │   ├── BaseUrlField.tsx                # label "Fill to /v1"
│   │   │   ├── ModelField.tsx                  # [Load list] button + text input
│   │   │   └── TestConnectionButton.tsx        # 4 states: idle/testing/ok/error
│   ├── StepUserCard.tsx
│   │   ├── UserNameField.tsx
│   │   └── UserBioTextarea.tsx
│   ├── StepCharacterCard.tsx                   # 4-option segmented
│   │   ├── UseDefaultOption.tsx                # mode: use_default
│   │   ├── PickExistingOption.tsx              # mode: pick_existing
│   │   ├── CreateNewForm.tsx                   # mode: create_new
│   │   │   ├── AvatarUpload.tsx                # simple square crop only
│   │   │   ├── CharacterNameField.tsx
│   │   │   ├── PersonalityField.tsx
│   │   │   └── SystemPromptOverrideField.tsx
│   │   └── ImportSTImageOption.tsx             # mode: import_st
│   └── StepFooter.tsx                          # [Back] [Skip] [Next/Finish] buttons
└── stores/
    └── onboarding.ts                           # zustand store
```

### 6.2 Wizard state machine (zustand)

```ts
type WizardStep =
  | 'provider' | 'user_card' | 'character_card'
  | 'submitting' | 'completed' | 'error';

interface WizardState {
  step: WizardStep;
  current_step_index: 0 | 1 | 2;
  data: {
    provider: {
      preset_id: string | null;
      api_key: string;
      base_url: string;
      model: string;
      test_result: { ok: boolean; error: string | null; latency_ms: number | null } | null;
    };
    user_card: { name: string; bio: string };
    character_card: {
      mode: 'use_default' | 'pick_existing' | 'create_new' | 'import_st';
      picked_card_id: number | null;
      new_card: { name: string; avatar_file: File | null; avatar_path: string | null;
                  personality: string; system_prompt_override: string };
      st_file: File | null;
    };
  };
  errors: { provider?: string; user_card?: string; character_card?: string; submit?: string };

  setStep(step: WizardStep): void;
  setProviderField<K extends keyof Data['provider']>(k: K, v: any): void;
  setUserCardField<K extends keyof Data['user_card']>(k: K, v: any): void;
  setCharacterCardField<K extends keyof Data['character_card']>(k: K, v: any): void;
  next(): Promise<void>;
  back(): void;
  skip(): void;
  finish(): Promise<void>;
  reset(): Promise<void>;
}
```

### 6.3 State transitions

```
mounted (snapshot.onboarding.required=true)
  └─→ step=provider, current=0
       │ [Next] (D-D1: continue anyway if test failed)
       ▼
  step=user_card, current=1
       │ [Next]
       ▼
  step=character_card, current=2
       │ [Skip] OR [Finish]
       ▼
  step=submitting (POST onboarding.complete)
       │ ws: onboarding.completed
       ▼
  step=completed → router.push("/chat") → unmount
```

### 6.4 UI behavior matrix

| Behavior | Rule |
|---|---|
| Progress indicator | 3 dots: active=fill, completed=check, upcoming=outline |
| Preset grid | 4 columns × 7 rows for 25 (last row has 1); 240×120px cards; 16px gap |
| Disabled preset card | `deferred: true` (Google) → 50% opacity, tooltip "Available in a future phase" |
| Base URL field label | "Fill to /v1" (openai_compat, anthropic) or "Fill to /v3" (volcengine) |
| Model field [Load list] button | disabled if `model_list_url_suffix: null`; tooltip explains |
| Test connection states | idle / testing (1.2s pulse) / ok ("✓ 234ms") / error ("✗ auth_failed") |
| [Next] enabled (provider) | always; failure shows warning banner + button text → [Continue anyway] |
| [Next] enabled (user_card) | name.trim().length > 0 && bio.length > 0 |
| [Skip] visibility | only on character_card step |
| [Back] behavior | local state only; does not call backend |
| Avatar upload (PL2.1) | file picker, ≤2MB, jpg/png/webp, stored as `data/avatars/{uuid}.{ext}`; no rotation/zoom |
| ST PNG import | file picker → client-side PNG tEXt chunk parse → populate form; failure shows error toast |
| Reset | Settings → Advanced [Reset Onboarding] → POST onboarding.reset → on next start, wizard re-appears |

---

## 7. Backend handler split

```
src/server/handlers/
├── onboarding.py        # NEW
│   ├── async def onboarding_get_state() -> dict
│   ├── async def onboarding_complete_step(step: str, data: dict) -> dict
│   ├── async def onboarding_complete() -> dict
│   └── async def onboarding_reset() -> dict
├── provider.py          # NEW
│   ├── async def provider_list_presets() -> dict
│   ├── async def provider_create_builtin(preset_id, label, api_key, base_url, model) -> dict
│   ├── async def provider_test_connection(preset_id, base_url, api_key, model) -> dict
│   └── async def provider_fetch_models(preset_id, base_url, api_key) -> dict
├── chat.py              # existing
├── session.py           # existing (chat session management)
├── commands.py          # existing
├── tools.py             # existing
└── reflection.py        # existing
```

### 7.1 First-run detection in `ws_server.start()`

```python
async def start():
    config_path = Path("config/fsar.yaml")
    template_path = Path("config/fsar.yaml.template")
    if not config_path.exists():
        if not template_path.exists():
            raise RuntimeError("config/fsar.yaml.template missing — cannot bootstrap")
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(template_path.read_text(encoding="utf-8"), encoding="utf-8")
        log.info("First run: created config/fsar.yaml from template")
    cfg = FsarConfig.load(config_path)
    presets = load_presets(Path("data/presets/llm-providers.json"))
    # ... rest of server init
```

---

## 8. Testing Scope

### 8.1 Backend tests (21 minimum)

```
tests/server/
├── test_preset_loader.py            # 4 tests
│   ├── test_25_presets_load
│   ├── test_preset_schema_no_default_model_field
│   ├── test_preset_anthropic_no_model_endpoint
│   └── test_preset_google_deferred
├── test_onboarding_handler.py       # 7 tests
│   ├── test_first_run_creates_yaml_from_template
│   ├── test_get_state_required_when_completed_false
│   ├── test_get_state_not_required_when_completed_true
│   ├── test_complete_step_appends_to_completed_steps
│   ├── test_complete_sets_completed_true
│   ├── test_complete_requires_all_three_steps
│   └── test_reset_clears_completed
├── test_provider_handler.py         # 11 tests
│   ├── test_list_presets_returns_25
│   ├── test_create_builtin_writes_yaml
│   ├── test_create_builtin_uses_preset_family
│   ├── test_test_connection_openai_compat_200
│   ├── test_test_connection_openai_compat_401
│   ├── test_test_connection_openai_compat_timeout
│   ├── test_test_connection_anthropic_uses_user_model
│   ├── test_test_connection_anthropic_model_required
│   ├── test_test_connection_anthropic_401
│   ├── test_test_connection_google_deferred
│   ├── test_fetch_models_openai_compat
│   └── test_fetch_models_anthropic_empty_or_error
└── test_first_run_integration.py    # 1 test
    └── test_clean_start_triggers_wizard
```

### 8.2 Frontend tests (10 minimum)

```
frontend/src/
├── components/onboarding/
│   ├── WizardShell.test.tsx
│   ├── StepProvider.test.tsx
│   │   ├── test_renders_25_preset_cards
│   │   ├── test_google_card_disabled
│   │   ├── test_select_card_shows_detail_panel
│   │   ├── test_continue_anyway_button_text_on_test_failure
│   │   └── test_model_field_works_with_manual_input
│   ├── StepUserCard.test.tsx
│   └── StepCharacterCard.test.tsx
│       ├── test_4_options_switchable
│       └── test_skip_button_visible
├── stores/onboarding.test.ts
│   ├── test_next_validates_step
│   ├── test_back_doesnt_call_backend
│   ├── test_skip_only_works_on_character_card
│   └── test_finish_redirects_to_chat
└── pages/Onboarding.test.tsx
    └── test_renders_only_when_required_true
```

### 8.3 Manual E2E checklist (Slice 7)

- [ ] Delete `config/fsar.yaml` → start → wizard appears, yaml auto-created
- [ ] 25 preset cards render correctly
- [ ] OpenAI: real key → load models (4) → select one → test pass → Next
- [ ] Anthropic: real key → type model manually → test pass → Next
- [ ] User card: name + bio → Next
- [ ] Character card "use default" → Finish
- [ ] Land on /chat with FSAR-zh in topbar
- [ ] Send a message → receive non-empty reply
- [ ] Restart → wizard does NOT appear
- [ ] Settings → Advanced → Reset Onboarding → restart → wizard re-appears
- [ ] Character card "create new" → upload avatar (square crop) → save
- [ ] Character card "import ST image" → use a real ST PNG → fields populated
- [ ] Crash recovery: kill client mid-step-1 → restart → resume at step 2

---

## 9. Exit Criteria

| # | Verifiable | How |
|---|-----------|-----|
| EC-1 | `config/fsar.yaml` missing → auto-generated on first start | Manual: rm yaml → start → wizard |
| EC-2 | 25 preset cards render in grid | Visual + test_renders_25_preset_cards |
| EC-3 | Provider step end-to-end works | Manual: OpenAI real key, full flow |
| EC-4 | User card step enforces name + bio | Manual: empty submit → Next disabled |
| EC-5 | Character card 4 modes all work | Manual: each mode reaches Finish |
| EC-6 | Finish writes `onboarding.completed: true` | Manual: `cat config/fsar.yaml` |
| EC-7 | Finish redirects to /chat | Visual |
| EC-8 | Topbar shows default FSAR-zh | Visual |
| EC-9 | Real LLM call produces reply | Manual: send a message |
| EC-10 | Reset button re-triggers wizard | Manual: Settings → Advanced → Reset |

---

## 10. Risks

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|------------|--------|------------|
| R1 | 25 preset base URLs go stale (vendor renames domain) | Medium | Low | Presets are best-effort; user can override base_url; test connection catches breakage |
| R2 | Anthropic test with user-typed model fails but model actually exists (typo, etc.) | Medium | Medium | D-D1: test failure does not block wizard; user can [Continue anyway] |
| R3 | ST V2 PNG tEXt chunk parsing fails on non-standard cards | Medium | Low | PL2.0 StV2Parser already handles spec; D-D9: failure shows toast, wizard continues |
| R4 | 25 presets include providers that need VPN access in some regions | High | Low | User can change base_url; wizard does not enforce success |
| R5 | 25 cards first-paint performance | Low | Low | 4-column grid + lazy detail panel; PL2.0 emotion page already handles larger lists |
| R6 | First run race: 6 character cards + 1 user card seed | Low | Medium | PL2.0 `CardRepo.seed_builtins_if_empty` already idempotent; add explicit test |
| R7 | Concurrent wizard users sharing fsar.yaml | Low | Critical | FsarConfig.save uses file lock (PL2.0) |
| R8 | `${ENV_VAR}` expansion fails (env not set) | Medium | Medium | FsarConfig.add_provider supports it; test failure surfaces "env var not set" |

---

## 11. Out of Scope (deferred)

- LLM call per-family request body / headers (use `D:/hermes/hermes-agent` reference in PL2.5)
- Google Gemini live protocol (preset is `deferred: true`)
- Avatar circular crop + zoom + rotate (mirror `C:\WinTool\SillyTavern\SillyTavern` in PL2.7)
- Marketplace / community sharing
- Per-conversation user card override
- Provider family auto-detection from base URL

---

## 12. Open Questions

| # | Question | Owner | Blocker? |
|---|---|---|---|
| Q1 | Avatar crop UX scope (D-D10): mirror SillyTavern? | User (post-PL2.1) | No |
| Q2 | When user re-runs `onboarding.reset`, does it delete created cards or just unset defaults? | TBD | No (defer to manual smoke) |
| Q3 | Should `provider.create_builtin` validate model via fetch_models before save? | TBD | UX question |

---

## 13. References

- `docs/DESIGN.MD` §3 (PL2 Roadmap), §4 (Onboarding), §6 (Presets), §16.2 (PL2.1 spec)
- `docs/superpowers/specs/2026-07-09-pl2-0-persona-foundation-design.md` (PL2.0 card schema)
- `docs/superpowers/handoff-2026-07-03-p7-phase1-2.md` (P7.1/P7.2 baseline + P7.8 settings contract)
- `docs/superpowers/2026-07-03-p7-gui-design.md` §6.14 (Settings → Models tab)
- `D:/hermes/hermes-agent` — LLM call request body/headers reference (PL2.5+, not PL2.1)
- `C:\WinTool\SillyTavern\SillyTavern` — Avatar crop UX reference (PL2.7+, not PL2.1)
- `C:\WinTool\airi\packages\stage-ui\src\libs\providers\providers\` — Reference for 25 vendor metadata shapes

---

## 14. Task Breakdown (Slice Plan)

| Slice | Tasks | Effort | Dependencies |
|-------|-------|--------|--------------|
| 1. Preset infrastructure | 3 (JSON + loader + tests) | 2-3h | none |
| 2. First-run detection | 3 (gitignore + template + main.py + tests) | 2-3h | none |
| 3. Backend handler: provider | 3 (handler + dispatch + tests) | 4-6h | Slice 1 |
| 4. Backend handler: onboarding | 3 (handler + snapshot + tests) | 3-4h | Slice 2 |
| 5. Frontend foundation | 3 (route + store + WizardShell) | 3-4h | Slice 4 |
| 6. Frontend three steps | 6 (provider + user + character + footer + avatar + ST) | 8-12h | Slice 5, 3, 4 |
| 7. Integration + smoke | 2 (E2E + docs) | 2-4h | Slice 1-6 |
| **Total** | **23 tasks** | **24-36h** | ≈ 3-5 working days |

**Execution order:** Slice 1 || 2 → 3 → 4 → 5 → 6 → 7
**Parallel opportunities:** Slice 1 and Slice 2 are independent.

---

*End of spec. Once approved, transition to writing-plans skill for detailed implementation plan.*

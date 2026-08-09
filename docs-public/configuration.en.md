# Configuration Guide

> Language: [中文](configuration.md) | English

Nearly all of FSAR's runtime behaviour is driven by a single YAML configuration file. This page explains every section — its meaning, defaults, and accepted values.

## Where the config lives

| File | Role |
|---|---|
| `config/fsar.yaml.template` | The **read-only template** shipped with the repo; lists every option and its default |
| `~/.fsar/config/fsar.yaml` | **Your config**, copied from the template on first run |

- On first launch, if `~/.fsar/config/fsar.yaml` is missing, FSAR copies the template there.
- Afterwards you edit it through the GUI (onboarding wizard, settings pages) or by hand.
- Delete the whole `~/.fsar/` directory to reset FSAR to a clean state (config, memory, caches, and logs are all removed).

> All defaults below are taken from `config/fsar.yaml.template`.

---

## onboarding — wizard state

Tracks the first-run wizard's progress; normally maintained by the UI, no need to edit by hand.

```yaml
onboarding:
  completed: false        # whether the wizard is complete
  completed_at: null
  completed_steps: []
  skipped_steps: []
  started_at: null
  last_step: null         # last step visited
```

## agent — agent tier

```yaml
agent:
  tier: medium
```

`tier` controls how much reasoning/execution effort the agent loop spends. There are several grades (default `medium`, up to `ultra`); higher tiers invest more in tool use and planning.

> Note: `agent.tier` and `reflection.intensity` below are two unrelated "intensity" dials — do not confuse them.

## chat — default model

```yaml
chat:
  default_model:
    kind: model
    provider: ""    # provider name (matches an entry in llm.providers[])
    model: ""       # model name
```

The chat model used by new sessions. Leave empty to let the UI choose.

---

## security — the safety layer (important)

FSAR's core selling point is defense in depth. This section configures each layer. For the full mechanism, see [`SECURITY.md`](../SECURITY.md) at the repo root.

```yaml
security:
  hardline_disabled_classes: []   # disable certain hardline classes (A–I); all on by default
  power_user_mode: false          # power-user mode (relaxes some confirmations)
  custom_sensitive_paths: []      # extra sensitive paths (require confirmation)
  always_allow_paths: []          # paths always allowed without confirmation
```

- **hardline_disabled_classes**: the hardline guard is an unconditional command floor, split into nine classes A–I (disk destruction, system lifecycle, persistence, privilege escalation, resource exhaustion, service control, network-security config, fetch-and-execute, filesystem integrity). All are enabled by default; do not add entries here unless you fully understand the consequences.

### security.skills — skill safety

```yaml
  skills:
    review_required: true         # require review before running a skill
    subprocess_env:               # subprocess environment scrubbing
      enabled: true
      allow: [PATH, HOME, LANG, TMPDIR, SYSTEMROOT, USERPROFILE]  # allowlist
      strip_prefixes: [API_KEY, TOKEN, SECRET, AUTH]              # strip vars containing these
    llm_review:
      enabled: false              # additionally review skills with a small model
```

`subprocess_env` ensures that when a skill runs, the child process only sees allowlisted variables, and any variable whose name contains `API_KEY/TOKEN/SECRET/AUTH` is stripped — provider keys never leak into skill code.

### security.mcp — MCP server safety

```yaml
  mcp:
    review_required: true         # require review before installing/enabling an MCP server
    cwd_pinning:
      enabled: true               # pin the MCP server's working directory
      require_dir: true           # require an explicit directory
```

### security.egress — network egress control

```yaml
  egress:
    enabled: false                # off by default; when on, gates skill/command outbound connections
    mode: deny                    # deny = default-deny, only allowlist passes; allow = default-allow, only blocklist blocked
    allowlist:
      - "api.openai.com:443"
      - "api.anthropic.com:443"
      - "127.0.0.0/8"
    blocklist:
      - "*.onion"
      - "169.254.0.0/16"          # block link-local / metadata addresses
```

### security.redaction — output redaction

```yaml
  redaction:
    enabled: true
    max_string_length: 16384      # truncate over-long strings to avoid leaks/bloat
    patterns: []                  # extra redaction patterns
```

### security.memory — memory-write sanitization

```yaml
  memory:
    write_sanitization:
      enabled: true
      block_on_match: true        # refuse the write when a rule matches
      custom_patterns: []
```

Prevents secrets and other sensitive content from being written into long-term memory.

### security.file_read_blacklist — file-read blacklist

```yaml
  file_read_blacklist:
    enabled: true
    defaults: true                # default blacklist: ~/.ssh/*, ~/.aws/credentials, ~/.gnupg/*, *.key, *.pem, id_rsa
    extra_patterns: []            # additional patterns to forbid reading
```

### Other security switches

```yaml
  session:
    no_trust_mode: false          # disallow "trust for this session"; confirm every time
  small_agent_review:
    enabled: false                # second-opinion review of high-risk actions by a small model
```

---

## llm — LLM providers

```yaml
llm:
  active: ""          # name of the active provider
  providers: []       # list of providers, each with name/provider/base_url/api_key/model, etc.
```

- Supports OpenAI, Anthropic, Google, DeepSeek, and any OpenAI-compatible endpoint; local models via Ollama / LM Studio.
- A provider row may set `format: responses` to route calls through the OpenAI Responses API (`/v1/responses`) instead of chat completions. Setting an openai preset's family to "OpenAI Responses" in the GUI writes this automatically.

## tts — text-to-speech

```yaml
tts:
  active: ""           # active TTS provider
  autoplay: false      # automatically read replies aloud
  default_voice: ""
  providers: []
```

## asr — speech recognition

```yaml
asr:
  active: ""      # active ASR provider
  language: ""    # recognition language (empty = auto)
  providers: []
```

---

## social — social-platform bridge

The same engine can send/receive through Telegram, Feishu (Lark), and WeChat; each platform can independently override the character and user cards.

```yaml
social:
  telegram:
    enabled: false
    bot_token: ""
  feishu:
    enabled: false
    app_id: ""
    app_secret: ""
    verification_token: ""
    encrypt_key: ""
  wechat:
    enabled: false
    account_id: ""
    bot_token: ""
    base_url: ""
    character_card_id: null   # platform-specific character card (null = global)
    user_card_id: null
```

## memory — memory & reflection

```yaml
memory:
  short_term_window: 50          # recent messages kept in short-term memory
  reflection_interval_hours: 12  # minimum interval for idle-batch reflection (hours)
  reflection_intensity: medium   # reflection intensity (several grades; default medium)
  recall_max_chars: 2000         # max characters of recall injected into the prompt
  enable_rating_prompt: true     # prompt the user to rate replies
  embedder:                      # semantic embeddings (for semantic memory/recall)
    provider: ""
    base_url: ""
    model: ""
    api_key: ""
    timeout: 60
```

## llm_cache — LLM response cache

A two-tier cache (L1 in-memory + L2 persistent) that reduces duplicate calls and speeds up responses.

```yaml
llm_cache:
  enabled: true
  l1_max_entries: 256       # L1 (memory) max entries
  l1_ttl_seconds: 300       # L1 time-to-live
  l2_ttl_seconds: 86400     # L2 (persistent) time-to-live
  retention: short          # retention policy
  skip_vision: true         # skip requests containing images (do not cache)
  use_responses_api: false  # legacy override; prefer per-provider format="responses" in llm.providers[]
```

## gui — UI server

```yaml
gui:
  host: 127.0.0.1   # backend listen address (local-only by default)
  port: 8765        # browser at http://127.0.0.1:8765
```

## logging

```yaml
logging:
  level: INFO       # log level; logs written to ~/.fsar/data/logs/
```

## permissions — tool permissions

```yaml
permissions:
  mode: normal      # session mode: strict / normal / trust (affects when confirmation appears)
  tools: {}         # per-tool trust/ask/deny configuration
  path_rules: []    # path rules (a match denies)
```

`mode` together with the risk level decides whether a tool call proceeds, needs confirmation, or is denied. See the "Risk engine" section of [`SECURITY.md`](../SECURITY.md).

## mcp — MCP server list

```yaml
mcp:
  servers: []       # installed MCP servers (name, command, args, env, etc.)
```

## reflection — reflection triggers

```yaml
reflection:
  intensity: medium       # reflection intensity (4 grades; default medium)
  triggers:
    per_task: true        # reflect after each task
    on_failure: true      # reflect on failure
    idle_batch:           # idle-batch reflection
      enabled: false
      threshold_events: 20   # fire after this many events
      threshold_hours: 12    # or this many hours since last time
```

The three reflection modes can coexist: `per_task`, `on_failure`, and `idle_batch`. Reflection re-reads conversations and updates the user profile (explicit preferences / inferred traits / behavioural patterns), and the next session opens with that context.

## user / style — user & appearance

```yaml
user:
  display_name: ""        # user display name

style:
  theme: system           # theme: system / light / dark
  font_scale: 1.0
  density: comfortable    # density: comfortable / compact
  motion: subtle          # motion intensity
  locale: en              # UI language (en / zh-Hans / zh-Hant / ja / de / fr)
  per_page_overrides: {}  # per-page style overrides
```

## plugins / external_skills — extensions

```yaml
plugins: []           # plugins
external_skills: []   # external skills (Python skills in external directories)
```

---

## Further reading

- Full security model and vulnerability reporting: [`SECURITY.md`](../SECURITY.md)
- Contributing: [`CONTRIBUTING.md`](../CONTRIBUTING.md)
- Third-party licenses: [`THIRD_PARTY_LICENSES/`](../THIRD_PARTY_LICENSES/)

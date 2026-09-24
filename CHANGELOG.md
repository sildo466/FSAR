# Changelog

All notable changes to FSAR will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **Memory injection no longer truncates by position.** The assembled block was
  cut at 2000 characters, which both split items mid-sentence and starved
  `history` — the source holding most query-relevant recall — because profile
  and preferences were injected in full ahead of it. Recall results are now
  turned into individual candidates, judged per item, packed whole into one
  shared character budget across memory / strategy / experience, and regrouped
  by source when rendered. Operational tool-stat warnings still bypass the
  budget and are injected unconditionally.
- **Character mode runs its persona filter before the budget is allocated**, so
  the filter sees every candidate instead of only the survivors of a priority
  cut. It is also now fail-closed: if the filter cannot run, the character
  receives no memory rather than unfiltered memory. Agent mode keeps the
  priority-order fallback, where unfiltered recall is intended.

### Added

- **Optional memory judge endpoint** (`llm.judge` in `fsar.yaml`, *Models* tab
  in Settings). Point it at a JEV / System One evaluation endpoint to score
  injection candidates by relevance; leave all three fields empty to fall back
  to static priority order. `base_url` and `api_key` accept `${ENV_VAR}`.
- **Injection budget settings** (`memory.inject_*`), editable in
  Settings → Advanced. Defaults: 2400-character budget, 40 candidates judged,
  0.35 relevance floor, 600 characters per item.

### Removed

- `memory.recall_max_chars`, replaced by `memory.inject_budget_chars`. The old
  value was tuned for positional truncation and would badly under-allocate an
  atomic packer.

## [0.5.0] - 2026-09-05

Minor release delivering the **Live Companion**: a spoken, voiced conversation
with an on-screen avatar. Reachable as the `Live` entry in the sidebar
(`/live`), it turns the existing ASR → chat → TTS pipes into a perceived
companion — pick a character + user + model in the lobby, then talk.

### Added

- **Live session lobby** — `/live` route with character / user / model
  selectors; picking *None (geometric)* uses the built-in fallback avatar.
- **VRM avatar rendering** — `AvatarRenderer` interface with a `VrmAvatar`
  implementation (`three-vrm`) that loads a user-supplied `.vrm` from
  `data/models/`, idles with procedural breath + blink, and drives the mouth
  and expressions from live state.
- **Geometric fallback avatar** — a breathing black icosahedron so the page
  always has a living presence even with no model selected.
- **Voice conversation loop** — browser mic capture with an energy-based VAD
  (replacing the unreliable ONNX Silero detector), ASR transcription, companion
  chat reply, and TTS playback; a **mute toggle** halts listening immediately.
- **Live subtitles** — a right-side panel showing user and FSAR lines as they
  stream, with a show/hide toggle and glass animation.
- **Lip-sync + emotion-driven expression** — the avatar's mouth follows the
  spoken reply (`wlipsync` on the TTS audio); expression blend shapes react to
  the numeric emotion layer (mood / affection / trust / energy).
- **Audio visualizer** — top waveform driven by the real TTS spectrum, plus a
  mic level meter for VAD/ASR diagnostics.
- **Live2D backend (Stage 4)** — `Live2DAvatar` behind the same
  `AvatarRenderer` interface (`pixi-live2d-display` + Cubism Core), with a
  VRM | Live2D grouped selector in the lobby. Live2D models are user-supplied
  folders in `data/models/` (`.model3.json`); the Cubism Core runtime is
  deliberately **not bundled** (see below).
- **`/api/models` Live2D support** — the read-only model endpoint now lists and
  serves Live2D folders recursively alongside VRM, keeping the existing
  traversal guard.
- **`liveScene` skin token** — a new background token (default `deepspace`, a
  dark radial gradient with drifting motes) for the live conversation page.
- **Character-mode replies in Live** — the voice turn reuses the character's
  configured voice and speaks brief replies.

### Docs

- New `THIRD_PARTY_LICENSES/pixi.js.txt` + `pixi-live2d-display.txt` and a
  README section documenting the Stage 4 stack. **Live2D Cubism Core is
  proprietary and not redistributed** — users download it themselves to
  `frontend/public/assets/live2d/`; without it, Live2D selection falls back to
  the geometric avatar.
- README (all six languages) and `docs-public/` updated with Live2D setup
  instructions.

## [0.4.1] - 2026-08-26

Patch release fixing tool-result redaction, shell-wrapper variable eating, PowerShell 5.1 encoding, and sandbox path mis-detection.

### Fixed

- **Screenshots / large tool results were silently destroyed** — the tool-result redactor truncated every string at `max_string_length` (4096 in the default config) and its bare base64-run pattern replaced the entire PNG payload with `[REDACTED:api_key_pattern]`, so `cu_screenshot` and other base64/file outputs reached the LLM as 26 bytes. Truncation is removed and binary payloads (pure base64 blobs, `data:` URIs) pass through untouched; the over-broad base64-run regex was replaced with context-anchored secret patterns (`api_key = ...`, `token: ...`).
- **run_command ate `$` variables** — a command already wrapped as `powershell -Command "$p = ..."` was executed through another `powershell -Command` layer, so the outer shell interpolated every `$var`/`$_` to empty before the inner command ran. Redundant shell wrappers (`powershell -Command "..."`, `bash -c "..."`, `cmd /c "..."`) are now unwrapped before execution, and the tool description tells the model to pass raw scripts.
- **PowerShell 5.1 encoding mojibake** — commands are now sent via `-EncodedCommand` (base64 UTF-16LE), so non-ASCII text and `$variables` survive 5.1's ANSI argv round-trip; `pwsh` (PowerShell 7+) is auto-detected when installed; 5.1 additionally gets UTF-8 shims (`[Console]::OutputEncoding`, `$OutputEncoding`, `$PSDefaultParameterValues['*:Encoding'] = 'utf8'`, `$ProgressPreference`) so stdout and `Out-File`/`Set-Content`/`Export-Csv` no longer emit GBK/UTF-16 garbage; output decoding sniffs UTF-8/UTF-16 BOMs before codepage fallbacks.
- **Sandbox path extraction produced synthetic paths** — the drive-letter regex matched inside multi-letter tokens (`HKLM:\SOFTWARE\...` yielded `M:\SOFTWARE\...`), quoted paths with spaces were truncated at the first space (`'C:\Program Files\Tencent'` → `C:\Program`), and those garbage tokens could be persisted into `security.always_allow_paths` on "allow always". Extraction now keeps quoted paths whole, blocks drive letters preceded by letters, scans unquoted text with quoted regions stripped, and `command_verdicts` drops absolute tokens that do not exist on disk.

### Docs

- README (all six languages) and `docs-public/` updated for v0.4.0: the `fsar` full-screen Textual TUI replaces the old terminal CLI section (slash commands, live status bar, cwd sandbox binding, `fsar agent|character|companion` modes), plus the In Character chat mode bullet; new `docs-public/modules/cli.md` / `cli.en.md` pages.

## [0.4.0] - 2026-08-25

First stable release of the 0.4.0 line, graduating from `v0.4.0-beta1`–`v0.4.0-beta3`. Highlights: a full-screen terminal TUI, an **In Character** mode, slash commands, and accurate live token + prompt-cache accounting.

### Added

- **Terminal TUI** — full-screen Textual UI (`fsar`) with a bottom status bar (mode + live context usage), cwd sandbox binding, and a startup runtime summary.
- **In Character (本色) mode** — a third chat mode where the assistant fully inhabits the selected character card: personality-driven agency (may refuse / stall / bargain), intent-based tool discovery via a router meta-tool that unlocks matching abilities for the rest of the session, and per-conversation persistence of unlocked tools. Long-term memory is filtered through an LLM cleanser so characters only learn plausible facts (fail-closed).
- **Slash commands** — interactive `/model`, `/character`, `/user`, `/tier`, `/effort`, `/compact`, `/new` (replaces `/reset`), plus `/use` for skills. Predictions are derived from the live tool/registry and browsable with the arrow keys.
- **Live token accounting** — GUI top-bar token gauge and TUI readout report real per-conversation context usage, persisted across restarts and navigation.
- **Prompt-cache transparency** — per-LLM-call cache token recording (cache read / cache creation) and a cache-hit-rate section in the usage view.
- **GUI usage trend chart** — recharts-based token/cost trend chart replacing the hand-rolled one.
- **Vision-model config** — standalone vision-model settings section with i18n labels and WS message types.
- **Real LLM conversation compaction** — `/compact` now runs genuine compaction instead of a stub.

### Fixed

- **Cache reads were always 0** — `normalise_usage` only inspected a nested dict, but the OpenAI SDK returns `PromptTokensDetails` as an object and DeepSeek reports hits in top-level `prompt_cache_hit_tokens`. Both paths now resolve correctly, so cache-read tokens and the hit rate show real numbers for OpenAI / DeepSeek / Responses / Gemini.
- Provider attribution — `provider_id` is now passed to every `chat_completion` caller so usage is billed to the right provider.
- Agent ultra/debate — peer conclusions now reach the coordinator and the debate path is reachable; self-check turns are no longer mis-flagged on non-streaming turns.
- GUI — persisted chat mode across navigation, compacted y-axis tick labels, renamed the fresh-input legend.
- WS — token refreshes on any disconnect; rejected-connection diagnostics added.
- TUI — eliminated launch/response delays, fixed popup DuplicateId errors, suggestion-row fitting for long CJK descriptions, and explicit sandbox preservation.

### Changed

- The `fsar` console entry now points at the terminal TUI.

## [0.3.0] - 2026-08-18

### Added

- **Skin system** — the headline of this release: a skin is a single `skin.json` that drives the whole appearance.
  - Data layer: skins live under `data/skins/<id>/` (built-in presets) or `~/.fsar/data/skins/<id>/` (personal, never committed); `skin.list` / `skin.set_active` WS handlers + `style.skin_id` persistence; a read-only `/skin-assets/<id>/<file>` route (with path-traversal protection) serves wallpapers and textures.
  - Resolve pipeline: `resolveSkin` layers `elements` → `palette` → built-in defaults for `base: "light" | "dark"`, so a skin can override any subset.
  - Global palette: 17 color tokens (`bg/surface/text/border/glass/glow/success/warning/danger/accent` …).
  - Per-element customisation: `elements` for `input/button/switch/chip/card` — each component class can be recolored independently, plus per-element image textures (`image` + `imageOpacity`).
  - Chat wallpaper: `background.chatImage` + `chatOverlay` (overlay = the skin's resolved `bg`, so text stays readable on any image).
  - Global texture: `pattern` lays a faint `background-image` over the app, visible through glass panels.
  - Full component coverage: buttons (Pill + IconButton + all inline solid buttons), inputs/selects/textareas, switches (new `Switch` primitive + migrated toggles), tag pills, and glass cards all consume element tokens.
  - New `--accent` token adopted by primary buttons and the send button; a `Settings → Appearance → Skin` selector with three built-in presets (warm / night / minimal).
  - Public authoring guide: `docs-public/modules/skin.md` + `skin.en.md`.
- **Experience / skill-compliance** — auto-sync skills from disk (`skill_sync`), a mechanical skill-compliance gate with forced redo (`skill_gate`), `/use` now attaches the full `SKILL.md`, and `experience_view` is forced via prompt with skill-directory access detection.
- **Chat**: a floating jump-to-bottom button appears when scrolled more than 300px from the latest message; it smooth-scrolls back to the newest content.

### Fixed

- Skin: the globally-shared `.glass` utility no longer injects positioning or a `::before` texture layer — previously this shifted top-bar/nav layout and dropped the history panel. Textures now live only on explicit card surfaces.
- Skin: patch-tint was dropped from the app texture so a missing pattern image leaves no residual overlay mask.
- Skin: active skin hydrates only on boot, not on every `config` change — unrelated settings changes no longer revert the selected skin.
- Skin: personal assets are served from `~/.fsar` home first, so user wallpapers never enter the remote repository.

## [0.2.4] - 2026-08-14

### Added

- Agent: the decision process now streams live to the frontend — reasoning text streams token-by-token and tool-call blocks attach in real time, instead of a black box that only dumps the final conclusion
- Chat: the sandbox pill stays enabled before the first message; picking a workspace pre-binds the new conversation to it (previously disabled until a message was sent)
- Experience: `experience_view` for external skills now attaches the authoritative `SKILL.md` from the skills root (path derived from the skill name, never stored) plus a conflict rule, so the agent reads the real spec instead of only a lossy summary; degrades to the summary alone when the skill directory is missing

### Removed

- L1/L2 LLM response cache: the exact-match disk cache never hit in agent/chat loops (messages mutate every turn, so the full-payload key always differs), making it pure per-call overhead. Provider-side prompt caching is preserved (Gemini cachedContents, Anthropic cache_control, Responses API `prompt_cache_key`).

### Fixed

- Agent: the stream pump could hang forever when the provider stalled — no timeout meant a blocked LLM call froze the whole loop with no error. A 120s no-output guard now aborts the turn with a visible note.
- Agent: self-check turns returned their own "检查完成 ✅" review report as the final answer even for simple Q&A; the pre-check answer is returned instead, self-check turns no longer stream, and the verification prompt explicitly forbids checklist output.
- Agent: non-iterable stream responses (some providers return a complete response despite `stream=True`) no longer inject a corrupt "LLM stream failed" string into the reply.
- run_command / process / skills: killing a timed-out command only killed the direct child, leaving grandchildren holding the stdout/stderr pipe and hanging the call; process-tree kill (`taskkill /F /T` on Windows, `os.killpg` on POSIX) is now used.
- Usage: the frontend cache-breakdown section referenced the removed L1/L2 cache; it and the orphaned `Bar` component were dropped.

## [0.2.3] - 2026-08-13

### Fixed

- Reflection: per-task reflections (GUI and CLI) always ran the rule-based fallback because the LLM was never wired into the task reflector — every record ended up as boilerplate like "Continue using chat.llm for similar tasks". Both paths now inject the active LLM client, and the task-reflection call's `max_tokens` was raised so reasoning models don't exhaust the budget on `reasoning_content` and return empty output. Reflections now carry specific, tool-named analysis and actionable suggestions.

## [0.2.2] - 2026-08-11

### Fixed

- Onboarding: Google Gemini was locked out of the model-selection screen. The `google` preset carried a stale `deferred: true` flag from before the Gemini family was wired into the chat engine; it now ships unlocked, and Test Connection gained a native Gemini probe (models list via `?key=` query param) instead of reporting an unknown error.

## [0.2.1.1] - 2026-08-11

### Fixed

- Build: TTS / ASR provider presets were swallowed by the `data/presets/*` gitignore rule and never shipped with the repo, so a fresh clone failed the frontend TS build with TS2307 (`speech-presets.ts`). Both JSON catalogs are now tracked.

## [0.2.1] - 2026-08-11

### Added

- Workspace: configurable output directory (`workspace.output_dir`, defaults to `~/FSAR-workspace`) where the agent saves generated files — documented in the configuration guide
- Chat: the agent's tool-call stream keeps running in the background while you navigate to other pages; returning to a conversation restores the current progress

### Fixed

- Chat: small-agent review no longer blocks every tool call when a reasoning model (e.g. deepseek) returns an empty verdict — reviewers get an unbounded token budget and empty responses are treated as "review unavailable"
- Memory: semantic recall is now scoped to the current character, so switching personas no longer leaks another character's conversation history
- Usage: the per-provider table now reports real token usage per provider instead of attributing the grand total to the active provider
- Chat: `/use <name> [task...]` splits the experience name from a trailing task and routes the task through the agent
- UI: chat greeting no longer shows a redundant second line
- Sandbox: the agent saves generated output files into the configured workspace instead of the Desktop

## [0.2.0] - 2026-08-10

### Added

- Card selectors: right-click an option to set it as the default card (character and user), persisted across restarts
- "Set as default" button in the character and user card editors

### Fixed

- Chat: first message in a fresh conversation no longer loses its user bubble when the server creates the conversation

## [0.1.0] - 2026-08-09

### Added

- Local-first AI companion core: persona cards, adaptive memory, and three reflection modes (per-task / on-failure / idle-batch)
- Layered security: hardline guards, risk engine, workspace gate, and env scrubber
- Tool ecosystem: shell, file ops, sandbox, Exa MCP web, image/PDF analysis, and computer use
- Skill persistence as SQLite experience rows
- Social bridge: Telegram / Feishu / WeChat
- Scheduler: timed and recurring jobs delivered to social targets
- LLM providers: OpenAI / Anthropic / Google / DeepSeek / OpenAI-compatible / Ollama / LM Studio, with an L1+L2 response cache
- TTS / ASR provider support
- i18n: 简体中文 / 繁體中文 / English / 日本語 / Deutsch / Français
- Tauri 2 + React frontend

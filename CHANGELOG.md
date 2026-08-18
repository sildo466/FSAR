# Changelog

All notable changes to FSAR will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

# Changelog

All notable changes to FSAR will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

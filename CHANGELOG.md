# Changelog

All notable changes to FSAR will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

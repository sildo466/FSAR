# Frontend `frontend/`

> Language: [中文](frontend.md) | English · Back to [module index](README.en.md)

A Vite + React app (package `fsar-gui`); the Tauri desktop shell is in `frontend/src-tauri`.

- **`pages/`** — top-level screens: Chat, Cards, Memory, Reflection, Insights, Library, Integration, Scheduler, Settings, SettingsWorkspace, Usage, Onboarding.
- **`clients/` and `lib/ws-client.ts`** — JSON WS protocol clients (the latter is the typed mirror of `src/server/events.py`).
- **`components/`** — grouped by feature: `chat/` (MessageList, RiskConfirm, AgentActivity, HistoryPanel, MicButton, SlashPopover, TierSwitcher, etc.), `onboarding/` (the `WizardShell` wizard: language → provider → ASR → TTS → embedding → character card → user card), `settings/` (MCP / permissions / embedding / style / advanced / provider modal), `workspace/` (sandbox-escape modal, security panels), `shell/` (sidebar / topbar).
- **`stores/`** — state stores (ws, chat-ui, cards, sessions, onboarding, workspace, locale, social, etc.) with Vitest tests alongside.
- **`locales/`** — i18n for en / zh-Hans / zh-Hant / ja / de / fr.

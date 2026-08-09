# 前端 `frontend/`

> 语言：中文 | [English](frontend.en.md) · 返回 [模块索引](README.md)

Vite + React 应用（包名 `fsar-gui`），Tauri 桌面壳在 `frontend/src-tauri`。

- **`pages/`** — 顶级页面：Chat、Cards、Memory、Reflection、Insights、Library、Integration、Scheduler、Settings、SettingsWorkspace、Usage、Onboarding。
- **`clients/` 与 `lib/ws-client.ts`** — JSON WS 协议客户端（后者是 `src/server/events.py` 的类型化镜像）。
- **`components/`** — 按特性分组：`chat/`（MessageList、RiskConfirm、AgentActivity、HistoryPanel、MicButton、SlashPopover、TierSwitcher 等）、`onboarding/`（`WizardShell` 向导：语言 → 提供商 → ASR → TTS → 嵌入 → 角色卡 → 用户卡）、`settings/`（MCP / 权限 / 嵌入 / 样式 / 高级 / 提供商弹窗）、`workspace/`（沙盒逃逸弹窗、安全面板）、`shell/`（侧栏 / 顶栏）。
- **`stores/`** — 状态存储（ws、chat-ui、cards、sessions、onboarding、workspace、locale、social 等），附带 Vitest 测试。
- **`locales/`** — en / zh-Hans / zh-Hant / ja / de / fr 国际化。

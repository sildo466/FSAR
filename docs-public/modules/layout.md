# `data/` 与 `config/`

> 语言：中文 | [English](layout.en.md) · 返回 [模块索引](README.md)

**`config/`**（随库配置）：
- `fsar.yaml.template` — 引导模板（见[配置详解](../configuration.md)）。
- `permissions.yaml` — 由 `security/permissions.py` 解析为 `PermissionState`。

**`data/`**（随库内容 + 运行时数据库）：
- `presets/` — `llm-providers.json` / `asr-providers.json` / `tts-providers.json`（onboarding 向导的可选项）。
- `cards/` — 角色卡 `FSAR-en/zh`、`coding-coach-en/zh`、`research-analyst-en/zh`、`default-user.json`、`_meta.json`。
- `emotion_default.json` — 默认情绪 schema 与公式。
- `skins/` — 随库皮肤预设（`warm`、`night`、`minimal`），各是一份手写 `skin.json`。
- `migrations/` — 带日期的 Python 迁移。
- 运行时产物：`memory.db`、`scheduler.db`、`llm_cache.db`、`tts_cache.db`、`chroma/`、`avatars/`、`logs/` 等。`memory.db` 以 WAL 模式运行，所以你还会在它旁边看到 `memory.db-wal` 与 `memory.db-shm`——它们是数据库的一部分，FSAR 运行时别动它们。

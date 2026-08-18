# Module Reference

> Language: [中文](README.md) | English

FSAR's backend lives under `src/`, the frontend under `frontend/`. This directory holds one page per module, describing its responsibility and key files.

> Convention: `prompt_archive.py`, `episodic_shim.py`, and similar legacy/compat code are omitted here.

## Backend `src/`

| Module | Role |
|---|---|
| [server](server.en.md) | WebSocket server & GUI chat engine |
| [core](core.en.md) | shared agent infrastructure |
| [memory](memory.en.md) | the memory system |
| [tools](tools.en.md) | the tool system |
| [security](security.en.md) | the security layer |
| [sandbox](sandbox.en.md) | workspace sandbox policy |
| [skills](skills.en.md) | reviewed local skill execution |
| [social](social.en.md) | social-platform bridge |
| [providers](providers.en.md) | LLM / ASR / TTS adapters |
| [mcp](mcp.en.md) | Model Context Protocol client |
| [utils](utils.en.md) | cross-cutting infrastructure |
| [scheduler](scheduler.en.md) | scheduled tasks |

## Frontend and data directories

- [frontend](frontend.en.md) — the Vite + React frontend app (Tauri desktop shell)
- [skin](skin.en.md) — the skin system: a hand-written `skin.json` recolors the site, adds a wallpaper, and customizes individual components
- [layout](layout.en.md) — shipped contents of `data/` and `config/`, plus the runtime databases

## What to read next

- [Project overview](../overview.en.md) · [Configuration guide](../configuration.en.md) · [Development tutorial](../development.en.md)
- [`SECURITY.md`](../../SECURITY.md) · [`CONTRIBUTING.md`](../../CONTRIBUTING.md)

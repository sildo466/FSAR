# FSAR

<p align="center">
  <img src="assets/icons/logo-wordmark.svg" alt="FSAR" width="380">
</p>

<p align="center">
  <strong>Faithful · Safe · Adaptive · Reflective</strong><br>
  A local-first AI companion that grows with you, not on you.
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License"></a>
  <img src="https://img.shields.io/badge/python-3.11+-3776AB.svg" alt="Python">
  <img src="https://img.shields.io/badge/Platform-linux%20%7C%20macOS%20%7C%20windows-lightgrey.svg" alt="Platform">
  <img src="https://img.shields.io/badge/LANG-Simplified%20Chinese-red.svg" alt="Simplified Chinese">
  <img src="https://img.shields.io/badge/LANG-Japanese-ff69b4.svg" alt="Japanese">
  <img src="https://img.shields.io/badge/LANG-English-lightgrey.svg" alt="English">
  <img src="https://img.shields.io/badge/LANG-German-ffd700.svg" alt="German">
  <img src="https://img.shields.io/badge/LANG-Traditional%20Chinese-orange.svg" alt="Traditional Chinese">
  <img src="https://img.shields.io/badge/LANG-French-0055A4.svg" alt="French">
</p>

> **Note:** The German and French translations are not yet 100% complete.

<p align="center">
  <strong>English</strong> ·
  <a href="README.zh-Hans.md">简体中文</a> ·
  <a href="README.ja.md">日本語</a> ·
  <a href="README.de.md">Deutsch</a> ·
  <a href="README.zh-Hant.md">繁體中文</a> ·
  <a href="README.fr.md">Français</a>
</p>

## What is FSAR?

FSAR is a local-first AI companion that **belongs to the user**, not to a vendor. Conversations, memories, decisions, and tools all live in a SQLite database under `~/.fsar/` on your own machine. Nothing is uploaded.

The name is the design contract: **F**aithful · **S**afe · **A**daptive · **R**eflective.

### The four pillars

- **Faithful** — FSAR is the character you configured (character card: name, personality, scenario, emotion state), talking to the user you described (user card). It does not drift into "generic assistant".
- **Safe** — Every tool call passes through layered checks: a hardcoded hardline guard blocks destructive shell commands (`rm -rf /`, `shutdown`, `mkfs`) before any other check; a risk engine classifies each tool as SAFE/LOW/MEDIUM/HIGH/CRITICAL; a workspace gate contains file access; a subprocess env scrubber strips API keys and tokens before running skills.
- **Adaptive** — Each tool call is logged. A strategy injector synthesises a `## Learned Strategies` block from the decision log and user model — *"Prefer `edit` over `file_ops write` when the file exists"* appears in the system prompt after the model itself has burned that lesson. An experience store persists procedural knowledge so an MCP server install from one session is recalled in the next.
- **Reflective** — Three reflection modes (per-task, on-failure, idle-batch) re-read conversations and update the user model: explicit preferences (e.g. "uses VSCode"), inferred profile ("often codes in the evening"), and recurring behavioral patterns. The next session opens with that context already in the system prompt.

### What it can do

- Run shell commands (PowerShell on Windows, bash elsewhere) with hardline guard
- Read, edit, search files in scoped workspaces
- Open apps and URLs via a sandboxed alias map
- Search and fetch the web via the free [Exa MCP](https://mcp.exa.ai) server — no API key required
- Analyze images and PDFs locally
- Operate your computer (Computer Use / cua): screenshot, click, type, keypress — gated separately
- Persist new skills as SQLite experience rows (P6) — one session's MCP install is the next session's recall
- Talk through Telegram, Feishu, or WeChat via the social bridge

## Quick Start

You need **Python 3.11+** and **Node.js 18+**. Install them with your platform's package manager (`brew install python@3.11 node`, `apt install python3.11 python3.11-venv nodejs`, or the Windows installers from python.org / nodejs.org).

### Clone and install

```bash
git clone https://github.com/sildo466/FSAR.git
cd FSAR
python3 -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Launch

| Platform | Command |
|---|---|
| Windows | `start.bat` |
| Linux / macOS | `./start.sh` |

The first launch installs frontend deps (`npm install`) and builds the UI (`npm run build`); subsequent launches skip the install step and rebuild in seconds.

### Terminal CLI

```bash
python main.py
```

Runs FSAR in your terminal — same memory, built-in tools, and safety gates, no browser UI. The loop itself is simpler than the WebUI's: a fixed tool budget, with no capability tiers, subagents, adversarial verification, micro-reflection, or context compaction. The interactive session takes slash commands (type `/help`; `/memory clear` wipes all memories). Installing with `pip install -e .` also provides an `fsar` console script.

Voice (TTS / ASR) and the social-platform bridges (Telegram / Feishu / WeChat) only run with the WebUI backend; the terminal covers chat, tools, memory, and scheduled jobs.

### Open

Browser opens to <http://127.0.0.1:8765>. If it does not, navigate there manually.

### macOS only: grant Computer Use permission

Open **System Settings → Privacy & Security → Accessibility** and grant access to your terminal app and Python. Required only for the Computer Use tools (`cu_screenshot`, `cu_click`, `cu_type`, `cu_keypress`).

### Stop

| Platform | Command |
|---|---|
| Windows | `taskkill /FI "WINDOWTITLE eq FSAR Backend*" /T /F` |
| Linux / macOS | `pkill -f "src.server.ws_server"` |

### Update

```bash
git pull
pip install -r requirements.txt --upgrade
```

Then re-launch.

## Highlights

What makes FSAR different from a generic AI chat app.

### Local-first

Your conversations, memories, and decision history all live in `~/.fsar/` — a SQLite database on your own machine. Nothing is uploaded to any FSAR server. The LLM provider only sees the messages you actually send it, same as with any chat client. Delete `~/.fsar/` and FSAR forgets everything.

### A character you defined, not a generic assistant

Every session runs a character card you wrote: name, personality, scenario, optional emotion state. Combine it with a user card describing yourself and the LLM gets a tightly-scoped persona, not "helpful AI assistant" that drifts off-topic. Swap the card, swap the character — no code change.

### It remembers you across sessions

After a few conversations, FSAR builds a stable profile: explicit preferences ("uses VSCode"), inferred behaviour ("often codes in the evening"), recurring patterns ("usually organizes downloads via file_ops"). The next session opens with that context already in the system prompt. You never re-explain yourself.

### It adapts to your style

Every tool call is logged. A strategy injector watches the data and synthesises a `## Learned Strategies` block that goes into future prompts — "Prefer `edit` over `file_ops write` when the file exists" appears after the model itself has burned that lesson. The longer you use FSAR, the better it gets at being *your* assistant.

### Defense in depth on the LLM

Even if the model hallucinates `rm -rf /` or `shutdown -h now`, a hardcoded guard short-circuits the entire tool pipeline before any sandbox check. Above that: a risk classifier (SAFE → CRITICAL), a workspace gate that contains file access, a subprocess env scrubber that strips API keys before running skills. Five layers between any LLM output and your filesystem.

### Bring your own model

OpenAI, Anthropic, Google, DeepSeek, or any custom OpenAI-compatible endpoint. Local models via Ollama or LM Studio work too. You pay the provider directly — no FSAR markup, no intermediary data layer. If you switch providers mid-session, FSAR swaps in the new client without losing state.

### Skills that persist

Install an MCP server (GitHub, Postgres, Slack, hundreds more) or a Python skill once. FSAR records the procedure as a row in the experience store — `active` → `stale` → `archived` state machine with auto-promotion. Next session, `experience_view` recalls it without re-installing.

### Multi-channel

The same engine talks through Telegram, Feishu (Lark), and WeChat. Each platform can override the character and user card independently — your Telegram FSAR persona can differ from your GUI FSAR persona without two installs.

### Computer Use, gated separately

A computer-use tier (`cua`) lets the model screenshot, click, type, and keypress on your desktop. The risk gate is separate from regular tools — and on macOS the OS itself requires explicit Accessibility permission.

### Small footprint

FSAR is compact and lightweight — a single Python service plus a slim Tauri frontend. No heavy runtime or cloud dependency; it runs comfortably on modest hardware.

## Tutorial

> 📖 This tutorial is a quick overview. For the full documentation — project overview, module reference, complete configuration guide, and the build/test/development walkthrough — see [`docs-public/`](docs-public/).

### Project layout

```
src/
  server/         FastAPI WebSocket transport
  core/           Agent loop, prompts, injectors
  memory/         short-term, long-term, semantic, user model, experience
  tools/builtin/  ~25 built-in tools
  security/       Risk engine, permissions, audit
  sandbox/        Hardline guard, workspace gate
  skills/         Python skill runtime
  social/         Telegram / Feishu / WeChat adapters
  providers/      LLM / TTS / ASR adapters
  utils/          Logger, config, migrations
frontend/         Tauri 2 / React UI
data/             SQLite + ChromaDB + logs + cache
config/           shipped yaml defaults
```

### Configuration

`fsar.yaml` is the single source of truth for runtime config.

- `config/fsar.yaml.template` — shipped defaults, read-only reference
- `~/.fsar/config/fsar.yaml` — your copy, edited by the UI or by hand

First run copies the template if your copy is missing. Sections: `llm` / `tts` / `asr` / `memory` / `security` / `social` / `mcp` / `reflection` / `permissions` / `user` / `style`. See [`config/fsar.yaml.template`](config/fsar.yaml.template) for the full schema with comments.

### Data layout

Everything FSAR remembers about you lives under `~/.fsar/`:

```
~/.fsar/config/        yaml files
~/.fsar/data/
  memory.db           conversations, decisions, user model, experience
  chroma/             semantic embeddings
  llm_cache.db        L1/L2 response cache
  tts_cache.db        TTS audio cache
  logs/               rotating log files
```

Delete `~/.fsar/` to reset FSAR to a clean state.

### Build and test

Python backend and the Tauri frontend are separate artifacts; there is no single "build" step.

```bash
# Backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Frontend (only needed when changing TS/React code)
cd frontend && npm install && npm run build

# Tests
pytest tests/ -q
```

Cross-platform tests live in `tests/test_*_cross_platform.py`.

## License

[MIT](LICENSE)


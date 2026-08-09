# Build · Test · Develop

> Language: [中文](development.md) | English

For developers who want to run, modify, or contribute to FSAR locally.

## 1. Prerequisites

| Dependency | Version | Notes |
|---|---|---|
| Python | 3.12+ | The project declares 3.11 minimum, but the Computer Use dependency `cua` requires `>=3.12,<3.14`, so use **3.12 or 3.13** in practice |
| Node.js | 18+ | Builds the frontend UI |

Install with your platform's package manager:

```bash
# macOS (Homebrew)
brew install python@3.12 node
# Debian / Ubuntu
sudo apt install python3.12 python3.12-venv nodejs
# Windows: installers from python.org / nodejs.org
```

## 2. Get the code and install dependencies

```bash
git clone https://github.com/sildo466/FSAR.git
cd FSAR
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

> Creating a virtual environment is optional — you may install the dependencies directly into your system Python.

> The backend (Python) and the frontend (Tauri/React) are two separate artifacts — **there is no single "build" step**.

## 3. Launch

| Platform | Command |
|---|---|
| Windows | `start.bat` |
| Linux / macOS | `./start.sh` (or `make dev`) |

The launch script will:

1. On first run, automatically `npm install` and `npm run build` the frontend (later runs skip install and rebuild in seconds);
2. Start the backend (`src.server.ws_server`) listening on `http://127.0.0.1:8765`;
3. Open the browser; if it does not, navigate there manually.

Useful `make` targets (see `Makefile`):

| Target | Effect |
|---|---|
| `make dev` | run `start.sh` (full launcher) |
| `make build` | build the frontend only |
| `make stop` | kill a running backend |
| `make test` | run `pytest tests/ -x -q` |
| `make clean` | remove build artifacts and caches |

### Terminal CLI (no browser)

```bash
python main.py    # or the fsar console script (needs `pip install -e .`)
```

Runs FSAR in a terminal: the same `~/.fsar/` data, built-in tools, and safety gates; the loop itself is simpler than the WebUI's (fixed tool budget — no capability tiers, subagents, adversarial verification, micro-reflection, or context compaction). The interactive session supports every slash command (type `/help`; e.g. `/memory clear` wipes all long-term memory after a confirmation prompt).

### Stop

| Platform | Command |
|---|---|
| Windows | `taskkill /FI "WINDOWTITLE eq FSAR Backend*" /T /F` |
| Linux / macOS | `pkill -f "src.server.ws_server"` |

### macOS extra step (Computer Use only)

Open **System Settings → Privacy & Security → Accessibility** and grant access to your terminal and Python. Only needed for the desktop tools (`cu_screenshot`/`cu_click`/`cu_type`/`cu_keypress`).

## 4. Frontend development

The frontend is **Tauri 2 + React + TypeScript**, under `frontend/`.

```bash
cd frontend
npm install
npm run build        # output is served statically by the backend
```

- `frontend/src/` — the React UI: `components/chat` (chat), `components/onboarding` (first-run wizard), `clients/` (WebSocket and HTTP clients).
- `frontend/src-tauri/` — the Tauri desktop shell (Rust); not required for pure web use.
- Component tests use Vitest/Testing Library (`*.test.tsx`).

You only need to rebuild the frontend when changing TS/React code.

## 5. Testing

The suite is designed to run **offline**: no network, no live MCP servers, no real LLM calls. `tests/server/conftest.py` stubs the engine's side effects to keep the server suite offline.

```bash
# Full suite (includes live-MCP / e2e tests)
pytest tests/ -q

# The offline unit gate CI runs (also the subset to run after changing security code)
pytest tests/sandbox tests/security tests/skills tests/utils tests/server -q

# A single file / a single test
pytest tests/sandbox/test_hardline.py -q
pytest tests/sandbox/test_paths.py::test_normalize_nfkc -q
```

Test layout:

```
tests/
  sandbox/    hardline, path normalization, sensitive paths, workspace gate
  security/   WebSocket auth
  skills/     skill runtime, egress, keys, review gate
  utils/      LLM factory egress
  server/     HTTP/WS endpoints (offline stubs)
```

Conventions:

- Add a test for any new behaviour or bug fix.
- Any change under `src/sandbox/` or `src/security/` must ship with tests under `tests/sandbox/` or `tests/security/` covering both the allow and the block path.
- Keep new tests offline; tests that genuinely need a live service must be guarded so the offline gate stays green.

## 6. Continuous integration

`.github/workflows/ci.yml` on push / PR:

1. ubuntu-latest + Python **3.12** (`cua` requires `>=3.12,<3.14`);
2. `pip install -r requirements.txt`;
3. Runs the offline unit gate `pytest tests/sandbox tests/security tests/skills tests/utils tests/server -q`.

> The dependency ranges carry upper bounds (e.g. `mcp>=1.0,<2`, `google-genai>=0.3,<2`) so CI does not leap to a new major the code is incompatible with. When upgrading dependencies, update these bounds and run the tests.

## 7. Code conventions

- **Python 3.12+**, with type hints where the surrounding code uses them.
- **Write comments and identifiers in English**; keep comments sparse — only explain non-obvious intent.
- **Do not write "fix bug" / "xxx changed" style comments** — history belongs in git and the CHANGELOG.
- There is no enforced formatter; consistency with neighbouring code is the rule.
- Keep changes surgical: touch only what your change requires; do not refactor or reformat unrelated code in the same commit.
- Runtime configuration flows through `fsar.yaml` (see the [configuration guide](configuration.en.md)); do not hardcode user paths or secrets.

## 8. Data and runtime directories

Everything about the user lives under `~/.fsar/`:

```
~/.fsar/config/        yaml configuration
~/.fsar/data/
  memory.db            conversations, decisions, user model, experience
  chroma/              semantic embeddings
  llm_cache.db         L1/L2 response cache
  tts_cache.db         TTS audio cache
  scheduler.db         scheduled tasks
  logs/                rotating logs + audit.log
```

Delete `~/.fsar/` to reset completely.

## 9. Commits & collaboration

- Use Conventional Commits: `feat(social): ...`, `fix(security): ...`, `docs: ...`.
- Open an issue first for substantial changes to agree on direction; small fixes can go straight to a PR.
- Keep PRs scoped to one concern; describe what changed and why, and link the issue.
- **Do not** report security vulnerabilities through public issues/PRs — use the private process in [`SECURITY.md`](../SECURITY.md).

## Further reading

- [Project overview](overview.en.md) · [Module reference](modules/README.en.md) · [Configuration guide](configuration.en.md)
- [`CONTRIBUTING.md`](../CONTRIBUTING.md) · [`SECURITY.md`](../SECURITY.md)

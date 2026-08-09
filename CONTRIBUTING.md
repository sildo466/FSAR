# Contributing to FSAR

Thank you for considering a contribution to FSAR — a local-first AI companion.
This document explains how to set up a development environment, the conventions
the codebase follows, and how to get a change merged.

By contributing you agree that your contributions are licensed under the same
[MIT License](LICENSE) that covers the project (inbound = outbound).

If you are reporting a security vulnerability, **do not open a public issue or
pull request** — follow the private disclosure process in [SECURITY.md](SECURITY.md).

## Getting started

You need **Python 3.11+** and **Node.js 18+**.

```bash
git clone https://github.com/sildo466/FSAR.git
cd FSAR
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

The backend and the Tauri/React frontend are separate artifacts; there is no
single build step.

```bash
# Run everything (installs frontend deps on first launch, then starts backend + UI)
./start.sh                       # Windows: start.bat   — or: make dev

# Frontend only (needed when changing TS/React code)
cd frontend && npm install && npm run build
```

The backend serves <http://127.0.0.1:8765>. Useful `make` targets:

| Target | Effect |
|---|---|
| `make dev` | run `start.sh` (full launcher) |
| `make build` | build the frontend only |
| `make test` | run `pytest tests/ -x -q` |
| `make stop` | kill a running backend |
| `make clean` | remove build artifacts and caches |

## Project layout

```
main.py             CLI entry point (console script `fsar`)
src/
  server/           FastAPI + WebSocket transport, chat engine, HTTP handlers
  core/             Agent loop, prompts, strategy / experience injectors
  memory/           short-term, long-term, semantic, user model, experience store
  tools/builtin/    built-in tools (shell, file ops, web, image, computer use)
  security/         risk engine, permissions, confirmation, audit, WS auth
  sandbox/          hardline guard, workspace gate, sensitive-path protection
  skills/           Python skill runtime + review gate, subprocess env scrubber
  social/           Telegram / Feishu / WeChat adapters
  providers/        LLM / TTS / ASR adapters
  mcp/              MCP server management
  utils/            config, logger, migrations, LLM cache
frontend/           Tauri 2 / React UI
tests/              pytest suite (see below)
config/             shipped yaml defaults (fsar.yaml.template)
data/               vendored presets / character cards (runtime data lives in ~/.fsar/)
```

## Coding conventions

- **Python 3.11+**, type hints where the surrounding code uses them.
- **Write comments and identifiers in English.** Keep comments sparse — only
  explain non-obvious intent; never narrate the obvious.
- **Do not leave "fix bug", "xxx changed", or changelog-style comments in the
  code.** History belongs in git and the CHANGELOG, not in comments.
- Match the existing style of the file you are editing. There is no enforced
  formatter; consistency with neighbouring code is the rule.
- Keep changes surgical: touch only what your change requires. Do not refactor
  or reformat adjacent code in the same commit.
- Runtime configuration flows through `fsar.yaml` (see
  [`config/fsar.yaml.template`](config/fsar.yaml.template)). Do not hardcode
  user-specific paths or secrets.

## Testing

The suite is designed to run **offline** — no network, no live MCP servers, no
real LLM calls. `tests/server/conftest.py` forces the server suite offline by
stubbing the engine's side effects.

```bash
pytest tests/ -q                 # full suite (includes live-MCP / e2e tests)
pytest tests/sandbox tests/security tests/skills tests/utils tests/server -q
                                 # the offline unit gate that CI runs
pytest tests/sandbox/test_hardline.py -q     # a single file
```

Guidelines:

- Add a test for any new behaviour or bug fix.
- Any change under `src/sandbox/` or `src/security/` **must** ship with tests
  under `tests/sandbox/` or `tests/security/` that cover both the allow and the
  block path. See [SECURITY.md](SECURITY.md) for the security-testing guidance.
- Keep new tests offline. If a test genuinely needs a live service, guard it so
  the offline gate stays green.

## Pull request process

1. Open an issue for substantial changes first, so we can agree on the approach
   before you invest the effort. Small fixes can go straight to a PR.
2. Create a topic branch off `main`.
3. Write focused commits. We use Conventional Commits, e.g.
   `feat(social): ...`, `fix(security): ...`, `docs: ...`.
4. Make sure `pytest` passes for the areas you touched and add tests where
   expected.
5. Open the PR against `main`. Describe **what** changed and **why**; link the
   related issue. Keep the diff scoped to one concern.
6. A maintainer will review. Address feedback by pushing new commits.

## Reporting issues

Bug reports and feature requests are welcome via GitHub Issues. Please include:

- FSAR version / git commit, OS, and Python version
- steps to reproduce, expected vs. actual behaviour
- the relevant log lines from `~/.fsar/data/logs/` (redact secrets first)

**Never** report security vulnerabilities through public issues or PRs — use
the private process in [SECURITY.md](SECURITY.md).

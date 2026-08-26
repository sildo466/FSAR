# Terminal TUI module (`src/cli/`)

> Language: [中文](cli.md) | English

The terminal frontend. v0.4.0 upgraded the early simple REPL into a full-screen Textual app. Entry point is `fsar` — the pyproject console script, i.e. `src.cli.tui:main` — or `python -m src.cli.tui`. Optional mode argument: `fsar agent` (default) / `fsar character` (In Character) / `fsar companion`.

| File | Responsibility |
|---|---|
| `tui.py` | The core `ChatApp` (Textual app): chat UI, startup summary, bottom status bar (chat mode + live context usage), cwd sandbox binding, slash-command dispatch |
| `tui_commands.py` | Command prediction: UI commands + engine commands derived live from the server handler registry + dynamic `/use <name>` entries for installed skills |
| `tui_screens.py` | Modal screens: model / character / user card pickers, tier, effort, permissions, etc. |
| `tui_widgets.py` | Hand-drawn widgets (input bar, message bubbles) |

The TUI shares the same `ChatEngine` (`src/server/chat_engine.py`) as the GUI, including `~/.fsar/` data, built-in tools, safety gates, and MCP sessions. Logs go to `~/.fsar/data/logs/fsar_cli_*.log`; the terminal itself shows only the Textual interface.
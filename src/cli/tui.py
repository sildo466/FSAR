# SPDX-License-Identifier: MIT
"""Terminal front-end (Textual TUI): drives the shared ChatEngine.

Replaces the rolling CLI with a full-screen Textual app — bottom-docked input
box with the assistant history scrolling above. The TerminalSink routes
ChatEngine events back into the UI via call_from_thread, so the same engine
path the GUI uses drives this terminal surface too.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

# Re-wrap stdout/stderr as UTF-8 so glyphs render on Windows (GBK console) and
# stay correct on Linux/macOS. No-op when the stream is already UTF-8.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Footer, Input, Markdown, Static

from src.security.confirmation import ConfirmResponse
from src.server.chat_engine import ChatEngine
from src.server.risk_bridge import RiskBridge
from src.utils.fsar_config import get_default_config
from src.utils.logger import logger

ASSISTANT_STYLE = ""
USER_STYLE = "bold"
MUTED = "dim"
ACCENT = "magenta"
LABEL = "cyan"
BORDER = "blue"
ERROR = "red"
WARN = "yellow"


class TerminalSink:
    """Stand-in for a FastAPI WebSocket that routes ChatEngine events into the
    Textual UI. The engine only calls ``send_json``/``send``, so this is the
    whole contract — plus a back-reference to the app for safe cross-thread UI
    updates.
    """

    def __init__(self, app: "ChatApp", bridge: RiskBridge) -> None:
        self.app = app
        self.bridge = bridge
        self._delta = ""
        self._anim: dict[str, Any] = {}
        self._pending_confirm_meta: dict[str, Any] | None = None

    async def send(self, data: Any) -> None:
        """Raw-string path is unused by the engine."""

    def _post(self, fn, *args) -> None:
        """Run a UI update. send_json runs inside a Textual worker, i.e. the app's
        own event loop on the UI thread, so we call directly (call_from_thread is
        only for cross-thread sends) and surface any render error instead of
        swallowing it — a silent failure here made replies invisible."""
        try:
            fn(*args)
        except Exception:
            logger.exception("UI update failed")

    async def send_json(self, payload: dict[str, Any]) -> None:
        _type = payload.get("type", "")

        if _type == "chat.delta":
            self._delta += payload.get("content") or ""
            self._post(self.app._stream_delta, self._delta)
            return

        if _type == "chat.thinking":
            self._post(self.app._add_status, "thinking…")
            return

        if _type == "agent.status":
            status = payload.get("status") or ""
            detail = (payload.get("detail") or "").strip()
            label = (payload.get("label") or "").strip()
            line = status
            if label:
                line += f" {label}"
            if detail:
                line += f" — {detail}"
            self._post(self.app._add_status, line)
            return

        if _type == "agent.plan.updated":
            items = payload.get("items") or []
            markers = {"pending": "[ ]", "in_progress": "[~]", "completed": "[x]"}
            lines = ["Plan:"]
            for item in items:
                mark = markers.get(item.get("status", "pending"), "[ ]")
                lines.append(f"  {mark} {item.get('content', '')}")
            self._post(self.app._add_status, "\n".join(lines))
            return

        if _type == "agent.context.compacted":
            before = payload.get("tokens_before")
            after = payload.get("tokens_after")
            self._post(
                self.app._add_status,
                f"context compacted ({before or '?'} → {after or '?'} tokens)",
            )
            return

        if _type == "chat.tool_call":
            await self._confirm_tool(payload)
            return

        if _type == "chat.tool_result":
            call_id = payload.get("call_id")
            result = payload.get("result") or ""
            preview = (result.replace("\n", " ").strip())[:200] or "(empty tool result)"
            # Re-render the assistant turn (a tool result may carry text).
            self._post(self.app._add_tool_result, preview)
            return

        if _type == "agent.run.started":
            self._post(self.app._add_status, f"agent started (tier={payload.get('tier')})")
            return

        if _type == "agent.run.finished":
            self._post(self.app._add_status, f"agent finished — {payload.get('outcome')}")
            return

        if _type == "chat.done":
            # End of an assistant turn: render the accumulated text as Markdown.
            text = self._delta
            self._delta = ""
            self._post(self.app._add_assistant, text)
            return

        if _type == "error":
            code = payload.get("code", "error")
            message = payload.get("message", "")
            self._post(self.app._add_error, f"{code}: {message}")
            return

        if _type == "conversation.created":
            session = payload.get("session") or {}
            sid = session.get("id") if isinstance(session, dict) else None
            if sid:
                self._post(self.app._add_status, f"session: {sid}")
            return

    async def _confirm_tool(self, payload: dict[str, Any]) -> None:
        """Blocking risk confirmation. In the TUI we cannot call input(), so we
        append the prompt to history and wait for the next Input submission to
        resolve bridge.submit(call_id, ...)."""
        call_id = payload.get("call_id")
        if not call_id:
            return
        tool = payload.get("tool") or "?"
        args = payload.get("args") or {}
        risk = payload.get("risk") or "SAFE"
        try:
            args_preview = json.dumps(args, ensure_ascii=False)[:400]
        except TypeError:
            args_preview = str(args)[:400]

        self._pending_confirm_meta = {
            "call_id": call_id,
            "tool": tool,
            "args": args_preview,
            "risk": risk,
        }
        prompt = (
            f"[bold yellow]FSAR wants to run:[/bold yellow] {tool} (risk={risk})\n"
            f"[dim]  args: {args_preview}[/dim]\n"
            "  [dim][y] approve  [n] deny  [all] trust tool this session  "
            "[never] permanently deny[/dim]"
        )
        self._post(self.app._add_confirm, prompt)

    def resolve_confirm(self, raw: str) -> None:
        """Called from the UI when the user submits y/n/all/never while a risk
        confirmation is pending."""
        if not self._pending_confirm_meta:
            return
        call_id = self._pending_confirm_meta["call_id"]
        raw = raw.strip().lower()
        if raw in ("all", "a"):
            response = ConfirmResponse.ALL
        elif raw in ("never", "v"):
            response = ConfirmResponse.NEVER
        elif raw in ("y", "yes"):
            response = ConfirmResponse.YES
        else:
            response = ConfirmResponse.NO
        self._pending_confirm_meta = None
        self.bridge.respond(call_id, response)


class ChatApp(App):
    """Full-screen Textual chat front-end for FSAR."""

    CSS = """
    #history {
        height: 1fr;
        border-bottom: heavy white;
        padding: 0 1;
    }
    #input {
        dock: bottom;
        height: 3;
        border: heavy white;
        margin: 0 1 1 1;
    }
    #input:focus {
        border: heavy cyan;
    }
    """

    def __init__(self, engine: ChatEngine, mode: str, bridge: RiskBridge) -> None:
        super().__init__()
        self.engine = engine
        self.mode = mode
        # Engine and sink MUST share the same bridge, or the engine's awaited
        # bridge.submit() never sees the sink's respond() and confirmation
        # deadlocks. main() hands in the same instance it gave ChatEngine.
        self.bridge = bridge
        self.sink = TerminalSink(self, self.bridge)
        self._conv_id: str | None = None
        self._live: Static | None = None

    def compose(self) -> ComposeResult:
        self.history = VerticalScroll(id="history")
        self.history.auto_scroll = True
        with self.history:
            yield Static("\n".join(_banner_lines()), id="banner")
        yield Input(placeholder="Message FSAR… (/help, /exit)", id="input")
        yield Footer()

    def on_mount(self) -> None:
        self._conv_id = self.engine.new_conversation()
        self.query_one("#input", Input).focus()
        self.run_worker(self._start_mcp(), exclusive=True)

    async def _start_mcp(self) -> None:
        try:
            await self.engine.start_mcp()
        except Exception as e:
            logger.error(f"MCP start failed: {e}")
            self.sink._post(self._add_error, f"MCP start failed: {e}")

    async def on_unmount(self) -> None:
        try:
            await self.engine.stop_mcp()
        except Exception as e:
            logger.error(f"MCP stop failed: {e}")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        input_widget = self.query_one("#input", Input)
        input_widget.value = ""
        if not text:
            return

        if text.startswith("/"):
            base = text.split()[0].lower()
            if base in ("/exit", "/quit"):
                self.exit()
                return
            if base in ("/fsar", "/attic"):
                self._add_status(
                    "00101111 01100001 01110100 01110100 01101001 01100011"
                    if base == "/fsar"
                    else (
                        "Traceback (most recent call last):\n"
                        '  File "<stdin>", line 1, in <module>\n'
                        "ModuleNotFoundError: No module named 'src.core.prompt_archive'"
                    )
                )
                return

        # A pending risk confirmation wants a y/n/all/never reply.
        if self.sink._pending_confirm_meta:
            self.sink.resolve_confirm(text)
            return

        self._add_user(text)
        self.run_worker(self._run_turn(text), exclusive=False)

    async def _run_turn(self, text: str) -> None:
        try:
            await self.engine.handle_send(
                self.sink, text, self.mode, conversation_id=self._conv_id,
            )
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"turn failed: {e}")
            self.sink._post(self._add_error, str(e))

    # ---- history updaters (run on the UI thread via call_from_thread) ----

    def _add_user(self, text: str) -> None:
        self.history.mount(Static(TextualPrefix(f"{text}", USER_STYLE)))

    def _add_assistant(self, text: str) -> None:
        if not text or not text.strip():
            return
        # Remove the transient streaming widget, then render the full reply.
        self._clear_live()
        self.history.mount(Markdown(text))

    def _add_status(self, text: str) -> None:
        self.history.mount(Static(f"[{MUTED}]{text}[/{MUTED}]"))

    def _add_confirm(self, text: str) -> None:
        self.history.mount(Markdown(text))

    def _add_tool_result(self, text: str) -> None:
        self.history.mount(
            Static(f"[{MUTED}]⚡ {text}[/{MUTED}]")
        )

    def _add_error(self, text: str) -> None:
        self.history.mount(Static(f"[bold {ERROR}]X[/bold {ERROR}] {text}"))

    def _stream_delta(self, text: str) -> None:
        # Keep ONE transient widget for the in-flight reply, updated in place,
        # final Markdown replaces it on chat.done. Avoids mounting a new Static
        # per delta (which flooded the history).
        if self._live is None:
            self._live = Static("")
            self._live.id = "live"
            self.history.mount(self._live)
        self._live.update(text)
        self.history.scroll_end(animate=False)

    def _clear_live(self) -> None:
        if self._live is not None:
            try:
                self._live.remove()
            except Exception:
                pass
            self._live = None


def TextualPrefix(text: str, style: str) -> str:
    """Prefix wrapper kept thin: the caller passes the raw text."""
    return f"[{style}]▸[/{style}] {text}"


def _banner_lines() -> list[str]:
    return [
        "  ███████╗███████╗ █████╗ ██████╗ ",
        "  ██╔════╝██╔════╝██╔══██╗██╔══██╗",
        "  █████╗  ███████╗███████║██████╔╝",
        "  ██╔══╝  ╚════██║██╔══██║██╔══██╗",
        "  ██║     ███████║██║  ██║██║  ██║",
        "  ╚═╝     ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝",
        "  Fully Self-evolving AI Companion",
        "",
        "  Type /help for commands, /exit to quit",
    ]


def main() -> None:
    """CLI/TUI entry point — build the shared ChatEngine and run the Textual app."""
    from src.utils.migrate import run_migration
    from src.utils.fsar_home import get_fsar_home
    from pathlib import Path

    # Keep FSAR's loguru chatter out of the terminal; it still goes to a file.
    from loguru import logger as _fsar_logger
    _fsar_logger.remove()
    _cli_log_dir = get_fsar_home() / "data" / "logs"
    _cli_log_dir.mkdir(parents=True, exist_ok=True)
    _fsar_logger.add(
        str(_cli_log_dir / "fsar_cli_{time:YYYY-MM-DD}.log"),
        rotation="00:00",
        retention="30 days",
        level="DEBUG",
        encoding="utf-8",
    )

    # Pin project root + cwd onto sys.path so data.* imports resolve regardless
    # of the launch directory (a console script can start from anywhere).
    _root = Path(__file__).resolve().parent.parent.parent
    for _p in (str(_root), os.getcwd()):
        if _p not in sys.path:
            sys.path.insert(0, _p)

    run_migration(_root)

    mode = "agent"
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args and args[0] in ("chat", "companion"):
        mode = "companion"
    elif args and args[0] == "agent":
        mode = "agent"

    config = get_default_config()
    bridge = RiskBridge()
    engine = ChatEngine(config, bridge)
    engine.card_repo.seed_builtins_if_empty()
    if engine.card_repo.get_default_character() is None:
        with engine.card_repo._connect() as conn:
            conn.execute(
                "UPDATE character_cards SET is_default = 1 "
                "WHERE id = (SELECT id FROM character_cards "
                "ORDER BY is_default DESC, name ASC LIMIT 1)"
            )
            conn.commit()

    # MCP start/stop run inside the App's own event loop (on_mount/on_unmount),
    # so main() only owns the blocking Textual run.
    app = ChatApp(engine, mode, bridge)
    app.run()


if __name__ == "__main__":
    main()

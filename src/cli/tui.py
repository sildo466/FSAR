# SPDX-License-Identifier: MIT
"""Terminal front-end: a TerminalSink that renders ChatEngine events to stdout,
plus the REPL loop that drives the shared ChatEngine (same stack as the GUI)."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

# Re-wrap stdout/stderr as UTF-8 before rich constructs its console, so glyphs
# render on Windows (GBK console) and stay correct on Linux/macOS. No-op when
# the stream is already UTF-8.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from rich.markdown import Markdown
from rich.panel import Panel

from src.security.confirmation import ConfirmResponse
from src.server.chat_engine import ChatEngine
from src.server.risk_bridge import RiskBridge
from src.utils.fsar_config import get_default_config
from src.utils.logger import logger
from src.utils.render import console

# Color tokens (Hermes-style) centralized so the palette is easy to tune.
TOK = {
    "label": "cyan",
    "border": "blue",
    "muted": "dim",
    "accent": "magenta",
    "text": "default",
    "ok": "green",
    "warn": "yellow",
    "error": "red",
}

USER_GLYPH = "▸"
ASSISTANT_GUTTER = "└─"


class TerminalSink:
    """Stand-in for a FastAPI WebSocket that renders ChatEngine events to the
    terminal instead of pushing them to a browser client.

    The engine only ever calls ``send_json`` on this object (never accept /
    receive / close), so implementing those two methods is the whole contract.
    """

    def __init__(self, bridge: RiskBridge) -> None:
        self.bridge = bridge
        # Accumulated assistant text for the in-flight turn
        self._delta = ""
        self._thinking_line = False
        self._awaiting_confirm: str | None = None

    async def send(self, data: Any) -> None:
        """Raw-string path is unused by the engine; keep it a no-op."""

    async def send_json(self, payload: dict[str, Any]) -> None:
        _type = payload.get("type", "")

        if _type == "chat.delta":
            self._delta += payload.get("content") or ""
            return

        if _type == "chat.thinking":
            if not self._thinking_line:
                console.print(f"[{TOK['muted']}]thinking…[/{TOK['muted']}]")
                self._thinking_line = True
            return

        if _type == "agent.status":
            status = payload.get("status") or ""
            detail = (payload.get("detail") or "").strip()
            label = (payload.get("label") or "").strip()
            line = f"[{TOK['muted']}]● {status}[/{TOK['muted']}]"
            if label:
                line += f" [bold]{label}[/bold]"
            if detail:
                line += f" — {detail}"
            console.print(line)
            return

        if _type == "agent.plan.updated":
            items = payload.get("items") or []
            markers = {"pending": "[ ]", "in_progress": "[~]", "completed": "[x]"}
            console.print(f"[{TOK['accent']}]Plan:[/{TOK['accent']}]")
            for item in items:
                mark = markers.get(item.get("status", "pending"), "[ ]")
                content = item.get("content", "")
                console.print(f"  {mark} {content}")
            return

        if _type == "agent.context.compacted":
            before = payload.get("tokens_before")
            after = payload.get("tokens_after")
            console.print(
                f"[{TOK['muted']}]context compacted[/{TOK['muted']}] "
                f"({before or '?'} → {after or '?'} tokens)"
            )
            return

        if _type == "chat.tool_call":
            await self._confirm_tool(payload)
            return

        if _type == "chat.tool_result":
            call_id = payload.get("call_id")
            if call_id and self._awaiting_confirm == call_id:
                self._awaiting_confirm = None
            result = payload.get("result") or ""
            preview = (result.replace("\n", " ").strip())[:200] or "(empty tool result)"
            custom_style = payload.get("custom_style")
            if custom_style:
                console.print(custom_style)
            else:
                console.print(
                    Panel(
                        f"[{TOK['muted']}]{preview}[/{TOK['muted']}]",
                        title="⚡",
                        border_style=TOK["muted"],
                        padding=(0, 1),
                    )
                )
            return

        if _type == "agent.run.started":
            console.print(
                f"[{TOK['muted']}]agent started[/{TOK['muted']}] "
                f"(tier={payload.get('tier')})"
            )
            return

        if _type == "agent.run.finished":
            console.print(
                f"[{TOK['muted']}]agent finished[/{TOK['muted']}] — {payload.get('outcome')}"
            )
            return

        if _type == "chat.done":
            # A complete assistant turn ended. Render the accumulated text as
            # Markdown with a Hermes-style gutter prefix.
            if self._delta and self._delta.strip():
                self._print_assistant(self._delta)
            self._delta = ""
            self._thinking_line = False
            return

        if _type == "error":
            code = payload.get("code", "error")
            message = payload.get("message", "")
            console.print(
                f"[bold {TOK['error']}]X[/bold {TOK['error']}] {code}: {message}"
            )
            return

        if _type == "conversation.created":
            session = payload.get("session") or {}
            sid = session.get("id") if isinstance(session, dict) else None
            if sid:
                console.print(f"[{TOK['muted']}]session: {sid}[/{TOK['muted']}]")
            return

        # Unknown event type — ignore silently.

    def _print_assistant(self, text: str) -> None:
        """Render the assistant reply as Markdown with a Hermes-style gutter."""
        console.print(f"[{TOK['border']}]{ASSISTANT_GUTTER}[/{TOK['border']}]")
        console.print(
            Markdown(text, code_theme="monokai", inline_code_theme="monokai")
        )

    async def _confirm_tool(self, payload: dict[str, Any]) -> None:
        """Blocking terminal risk confirmation. Paused mid-turn; the engine is
        awaiting bridge.submit(call_id, ...) so we resolve it with the user's
        choice here."""
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

        console.print(
            Panel(
                (
                    f"[{TOK['accent']}]{tool}[/{TOK['accent']}] "
                    f"(risk={risk})\n"
                    f"[{TOK['muted']}]args: {args_preview}[/{TOK['muted']}]\n\n"
                    "[y] approve  [n] deny  [all] trust this tool for this session  "
                    "[never] permanently deny"
                ),
                title=f"[{TOK['warn']}]FSAR wants to run[/{TOK['warn']}]",
                border_style=TOK["warn"],
                padding=(0, 1),
            )
        )

        self._awaiting_confirm = call_id

        loop = asyncio.get_running_loop()
        try:
            raw = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: input("  > ").strip().lower(),
                ),
                timeout=30.0,
            )
        except (asyncio.TimeoutError, EOFError):
            raw = "n"

        if raw in ("y", "yes"):
            response = ConfirmResponse.YES
        elif raw in ("all", "a"):
            response = ConfirmResponse.ALL
        elif raw in ("never", "v"):
            response = ConfirmResponse.NEVER
        else:
            response = ConfirmResponse.NO

        self.bridge.respond(call_id, response)


def _print_banner(engine: ChatEngine) -> None:
    """Faux-GUI startup banner, mirroring the legacy CLI look."""
    console.print()
    console.print("  ███████╗███████╗ █████╗ ██████╗ ")
    console.print("  ██╔════╝██╔════╝██╔══██╗██╔══██╗")
    console.print("  █████╗  ███████╗███████║██████╔╝")
    console.print("  ██╔══╝  ╚════██║██╔══██║██╔══██╗")
    console.print("  ██║     ███████║██║  ██║██║  ██║")
    console.print("  ╚═╝     ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝")
    console.print("  Fully Self-evolving AI Companion")
    console.print()
    console.print("  Type /help for commands, /exit to quit")
    console.print()


async def _run(engine: ChatEngine, sink: TerminalSink, mode: str) -> None:
    conv_id = engine.new_conversation()
    while True:
        try:
            loop = asyncio.get_running_loop()
            # Full-width white rule as the input box top border.
            console.rule(style="bold white")
            user_input = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: input("  ").strip()),
                timeout=None,
            )
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye![/dim]")
            return

        if not user_input:
            continue

        if user_input.startswith("/"):
            if user_input.split()[0].lower() in ("/exit", "/quit"):
                console.print("[dim]Goodbye![/dim]")
                return
            if user_input.split()[0].lower() in ("/fsar", "/attic"):
                if user_input.split()[0].lower() == "/fsar":
                    console.print("00101111 01100001 01110100 01110100 01101001 01100011")
                else:
                    console.print(
                        "Traceback (most recent call last):\n"
                        '  File "<stdin>", line 1, in <module>\n'
                        "ModuleNotFoundError: No module named 'src.core.prompt_archive'"
                    )
                continue

        # User message: colored glyph + bold body inside the input box.
        console.print(
            f"[bold {TOK['label']}]{USER_GLYPH}[/bold {TOK['label']}] "
            f"[bold]{user_input}[/bold]"
        )

        try:
            await engine.handle_send(
                sink, user_input, mode, conversation_id=conv_id,
            )
        except asyncio.CancelledError:
            console.print("\n[dim](Cancelled.)[/dim]")
            return
        except Exception as e:
            logger.error(f"turn failed: {e}")
            console.print(f"[bold red]X[/bold red] {e}")


def main() -> None:
    """CLI entry point — build the shared ChatEngine and run the terminal REPL."""
    from src.utils.migrate import run_migration
    from src.utils.fsar_home import get_fsar_home
    from pathlib import Path

    # Keep FSAR's loguru chatter out of the interactive terminal so logs never
    # interleave with conversation output. They still land in the log file.
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

    # Ensure the project root is importable regardless of the launch directory.
    # The engine imports migration modules under the ``data`` package at runtime
    # (e.g. SessionStore -> data.migrations.*), which only resolves when the
    # FSAR root is on sys.path. A console script can start from any cwd, so pin
    # both the project root and the cwd up front, before ChatEngine constructs.
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
    sink = TerminalSink(bridge)
    # A CLI session has no onboarding to seed cards, so make sure the built-in
    # character cards exist before the first turn (the GUI seeds these at
    # startup). Without them handle_send fails on "no character card available".
    engine.card_repo.seed_builtins_if_empty()
    # seed_builtins_if_empty only assigns is_default when inserting a fresh
    # FSAR/zh card; an existing card set that lacks a default leaves
    # get_default_character() as None, which breaks the agent turn. Pick the
    # first card as default when none is marked.
    if engine.card_repo.get_default_character() is None:
        with engine.card_repo._connect() as conn:
            conn.execute(
                "UPDATE character_cards SET is_default = 1 "
                "WHERE id = (SELECT id FROM character_cards "
                "ORDER BY is_default DESC, name ASC LIMIT 1)"
            )
            conn.commit()

    _print_banner(engine)

    async def _amain() -> None:
        await engine.start_mcp()
        try:
            await _run(engine, sink, mode)
        finally:
            await engine.stop_mcp()

    try:
        asyncio.run(_amain())
    except KeyboardInterrupt:
        console.print("\n[dim]Goodbye![/dim]")


if __name__ == "__main__":
    main()

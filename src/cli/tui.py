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
        """Risk confirmation. The engine sends a chat.tool_call for EVERY tool
        (even ones that don't need confirmation, marked risk=SAFE) — those must
        NOT raise an approval, or the Agent appears to run ahead of the user
        picking. Only genuinely risky tools (risk != SAFE) show the ConfirmBar
        and block, because only they await bridge.submit()."""
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

        # SAFE tools never block — the engine already ran them. Show status only.
        if risk == "SAFE":
            self._post(self.app._add_tool_status, f"{tool} — running…")
            return

        self._pending_confirm_meta = {
            "call_id": call_id,
            "tool": tool,
            "args": args_preview,
            "risk": risk,
        }
        self._post(self.app._show_confirm_bar, self._pending_confirm_meta)

    def resolve_confirm(self, choice: str) -> None:
        """Called from the ConfirmBar when the user picks an action."""
        if not self._pending_confirm_meta:
            return
        call_id = self._pending_confirm_meta["call_id"]
        mapping = {
            "approve": ConfirmResponse.YES,
            "deny": ConfirmResponse.NO,
            "trust": ConfirmResponse.ALL,
            "never": ConfirmResponse.NEVER,
        }
        response = mapping.get(choice)
        if response is None:
            return
        self._pending_confirm_meta = None
        self._post(self.app._hide_confirm_bar)
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
        self._suggestion_popup: Any | None = None

    def compose(self) -> ComposeResult:
        self.history = VerticalScroll(id="history")
        self.history.auto_scroll = True
        with self.history:
            yield Static("\n".join(_banner_lines()), id="banner")
        self.compose_suggestions()
        yield Input(placeholder="Message FSAR… (/help, /exit)", id="input")
        yield Footer()

    def compose_suggestions(self) -> None:
        """Mount the suggestion popup once; content updated in-place."""
        from src.cli.tui_widgets import CommandSuggestionPopup

        self._suggestion_popup = CommandSuggestionPopup([], id="cmd-suggestions")
        self._suggestion_popup.display = False
        self.mount(self._suggestion_popup)

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

    def on_input_changed(self, event: Input.Changed) -> None:
        """Show command suggestions when user types /"""
        from src.cli.tui_commands import CommandPredictor
        from src.cli.tui_widgets import CommandSuggestionPopup

        text = event.value
        if not text.startswith("/"):
            self._hide_suggestions()
            return

        predictor = CommandPredictor()
        suggestions = predictor.predict(text)

        if suggestions:
            self._update_suggestions(suggestions)
        else:
            self._hide_suggestions()

    def _update_suggestions(self, suggestions: list[tuple[str, str]]) -> None:
        """Update popup content in place and make visible."""
        if self._suggestion_popup is None:
            return
        self._suggestion_popup.set_suggestions(suggestions)
        self._suggestion_popup.display = True

    def _hide_suggestions(self) -> None:
        """Hide command suggestion popup."""
        if self._suggestion_popup is not None:
            self._suggestion_popup.display = False

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        input_widget = self.query_one("#input", Input)
        input_widget.value = ""
        self._hide_suggestions()
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
            if base == "/model":
                self._handle_model_command()
                return
            if base == "/character":
                self._handle_character_command()
                return
            if base == "/user":
                self._handle_user_command()
                return
            if base == "/tier":
                self._handle_tier_command(text)
                return
            if base == "/effort":
                self._handle_effort_command(text)
                return
            if base == "/compact":
                self.run_worker(self._handle_compact_command(), exclusive=False)
                return
            if base == "/new":
                self._handle_new_command()
                return
            if base == "/resume":
                self.run_worker(self._handle_resume_command(), exclusive=False)
                return
            if base == "/permissions":
                self._handle_permissions_command()
                return

        # Risk confirmation is handled exclusively by the ConfirmBar (it takes
        # focus, so the Input is not typable while an approval is pending).
        if self.sink._pending_confirm_meta:
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

    def _add_tool_status(self, text: str) -> None:
        self.history.mount(Static(f"[{ACCENT}]⚙ {text}[/{ACCENT}]"))

    def _show_confirm_bar(self, meta: dict[str, Any]) -> None:
        """Mount the approval bar over the input while a risky tool awaits a
        decision. The bar takes focus, so the Input is covered and untypable —
        this blocks until the user picks an action."""
        from src.cli.tui_widgets import ConfirmBar

        try:
            self.query_one("#confirm-bar").remove()
        except Exception:
            pass
        self.query_one("#input", Input).display = False
        bar = ConfirmBar(
            meta["tool"], meta["args"], meta["risk"],
            on_select=self.sink.resolve_confirm, id="confirm-bar",
        )
        self.mount(bar)

    def _hide_confirm_bar(self) -> None:
        try:
            bar = self.query_one("#confirm-bar")
            bar.remove()
        except Exception:
            pass
        self.query_one("#input", Input).display = True
        self.query_one("#input", Input).focus()

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
            # No fixed id: on a rapid resend the old widget's remove() may not
            # have flushed, and a duplicate id would raise DuplicateIds and
            # swallow the new turn. Mount without an id.
            self._live = Static("")
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

    # ---- command handlers ----

    def _handle_model_command(self) -> None:
        from src.cli.tui_screens import ModelSelectScreen

        models = self._list_available_models()
        if not models:
            self._add_status("No models available")
            return

        def on_selected(model: str | None) -> None:
            if model:
                self.engine._session_model_override = model
                self._add_status(f"Switched to model: {model}")

        self.push_screen(ModelSelectScreen(models), on_selected)

    def _handle_character_command(self) -> None:
        from src.cli.tui_screens import CharacterSelectScreen

        characters = [(c.name, c.id) for c in self.engine.card_repo.list_characters()]
        if not characters:
            self._add_status("No character cards available")
            return

        def on_selected(card_id_str: str | None) -> None:
            if card_id_str:
                card_id = int(card_id_str)
                character = self.engine.card_repo.get_character(card_id)
                if character:
                    self.engine._session_character_override = card_id
                    self._add_status(f"Switched to character: {character.name}")

        self.push_screen(CharacterSelectScreen(characters), on_selected)

    def _handle_user_command(self) -> None:
        from src.cli.tui_screens import UserSelectScreen

        users = [(u.name, u.id) for u in self.engine.card_repo.list_user_cards()]
        if not users:
            self._add_status("No user cards available")
            return

        def on_selected(user_id_str: str | None) -> None:
            if user_id_str:
                user_id = int(user_id_str)
                user_card = self.engine.card_repo.get_user_card(user_id)
                if user_card:
                    self.engine._session_user_override = user_id
                    self._add_status(f"Switched to user: {user_card.name}")

        self.push_screen(UserSelectScreen(users), on_selected)

    def _handle_tier_command(self, text: str) -> None:
        parts = text.split()
        if len(parts) != 2:
            self._add_status("Usage: /tier [low|medium|high|xhigh|max]")
            return

        tier = parts[1].lower()
        valid_tiers = {"low", "medium", "high", "xhigh", "max"}
        if tier not in valid_tiers:
            self._add_status(f"Invalid tier: {tier}. Use one of: {', '.join(valid_tiers)}")
            return

        self.engine._session_tier_override = tier
        self._add_status(f"Agent tier set to: {tier}")

    def _handle_effort_command(self, text: str) -> None:
        parts = text.split()
        if len(parts) != 2:
            self._add_status("Usage: /effort [low|medium|high|xhigh|max]")
            return

        effort = parts[1].lower()
        valid_efforts = {"low", "medium", "high", "xhigh", "max"}
        if effort not in valid_efforts:
            self._add_status(f"Invalid effort: {effort}. Use one of: {', '.join(valid_efforts)}")
            return

        self.engine._session_effort_override = effort
        self._add_status(f"Reasoning effort set to: {effort}")

    async def _handle_compact_command(self) -> None:
        """Compact the current conversation's in-memory short-term context.
        Full summarization is automatic inside agent runs; here we reset the
        volatile short cache so the next turn is built from persisted history."""
        self._add_status("Compacting conversation history...")
        try:
            conv_id = self._conv_id or self.engine.active_conversation_id()
            cache = getattr(self.engine, "_short_cache", None)
            before = len(cache.get(conv_id, ())) if cache else 0
            if cache and conv_id in cache:
                cache[conv_id].clear()
            self._add_status(
                f"History compacted ({before} → 0 short-term messages)."
            )
        except Exception as e:
            self._add_status(f"Compact failed: {e}")

    def _handle_new_command(self) -> None:
        """Start a fresh conversation (new session id, clear displayed history)."""
        banner = self.history.query_one("#banner", Static)
        for child in list(self.history.children):
            if child is not banner:
                child.remove()
        self._conv_id = self.engine.new_conversation()
        self._add_status("New conversation started.")

    async def _handle_resume_command(self) -> None:
        """List historical conversations for resumption."""
        from src.cli.tui_screens import ResumeSelectScreen

        rows = self.engine.session_store.list(limit=50)
        if not rows:
            self._add_status("No historical conversations found.")
            return

        def label(row) -> str:
            title = (row.title or "").strip() or row.id[:8]
            return f"{row.updated_at:%Y-%m-%d %H:%M} — {title}"

        sessions = [(label(r), r.id) for r in rows]

        def on_selected(conv_id: str | None) -> None:
            if conv_id:
                self.run_worker(self._do_resume(conv_id))

        self.push_screen(ResumeSelectScreen(sessions), on_selected)

    async def _do_resume(self, conv_id: str) -> None:
        ok = await self.engine.switch_conversation(conv_id)
        if ok:
            self._conv_id = conv_id
            self._add_status(f"Resumed conversation: {conv_id}")
        else:
            self._add_status(f"Failed to load conversation: {conv_id}")

    def _handle_permissions_command(self) -> None:
        """Configure sandbox permissions (sandbox path + approval mode)."""
        from src.cli.tui_screens import PermissionsScreen

        current_path = self.engine.config.get("security.sandbox.path") or os.getcwd()
        no_trust = bool(self.engine.config.get("security.session.no_trust_mode", False))
        current_mode = "manual" if no_trust else "auto"

        def on_result(result: dict[str, str] | None) -> None:
            if not result:
                return
            new_path = result.get("sandbox_path") or current_path
            new_mode = result.get("mode") or current_mode
            self.engine.config.patch("security.sandbox.path", new_path)
            self.engine.config.patch(
                "security.session.no_trust_mode", new_mode == "manual"
            )
            self.engine.config.save()
            self.engine.permissions.no_trust_mode = new_mode == "manual"
            self._add_status(f"Sandbox updated: {new_path} [{new_mode}]")

        self.push_screen(
            PermissionsScreen(current_path, current_mode, confirm_on_exit=True),
            on_result,
        )

    def _list_available_models(self) -> list[tuple[str, str]]:
        """Return [(display_name, provider:model), ...] for all configured models."""
        from src.utils.fsar_config import get_default_config

        config = get_default_config()
        providers = config.list_providers(enabled_only=True)

        models = []
        for provider in providers:
            provider_id = provider.get("id", "")
            label = provider.get("label", provider_id)
            model = provider.get("model", "")

            if provider_id and model:
                display = f"{label} ({model})"
                value = f"{provider_id}:{model}"
                models.append((display, value))

        return models


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

"""FSAR — Fully Self-evolving AI Companion

Main entry — CLI interaction loop.
Tool System + Computer Use: LLM-driven.
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Force UTF-8 on Windows console for non-ASCII input/output (e.g. Chinese).
if sys.platform == "win32":
    import io
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from openai import OpenAI

from src.security import RiskEngine, ask_user, load_permissions, save_permissions
from src.security.permissions import PermissionState
from src.server.chat_engine import ChatEngine
from src.server.risk_bridge import RiskBridge
from src.tools import ToolRegistry
from src.utils import render
from src.utils.config import get_config
from src.utils.logger import logger


class _ConsoleSink:
    """Stand-in for the websocket the engine streams to.

    Mirrors the event vocabulary ``src/cli/tui.py`` consumes, rendered to
    stdout. Only ``send_json``/``send`` are part of the contract.
    """

    def __init__(self, engine: ChatEngine) -> None:
        self.engine = engine
        self._delta = ""

    async def send(self, data) -> None:
        """Raw-string path is unused by the engine."""

    async def send_json(self, payload: dict) -> None:
        kind = payload.get("type", "")

        if kind == "chat.delta":
            self._delta += payload.get("content") or ""
            return

        if kind == "chat.done":
            text, self._delta = self._delta, ""
            if text.strip():
                render.md(text)
            return

        if kind == "chat.tool_call":
            # The engine emits this for every tool, marking the ones that ran
            # without approval as SAFE. Only the risky ones await the bridge.
            if (payload.get("risk") or "SAFE") != "SAFE":
                asyncio.create_task(self._confirm(payload))
            return

        if kind == "tool.sandbox.request_escape":
            asyncio.create_task(self._confirm_escape(payload))
            return

        if kind == "chat.tool_result":
            result = str(payload.get("result") or "").replace("\n", " ").strip()
            render.status("tool", result[:200] or "(empty)")
            return

        if kind == "agent.status":
            line = str(payload.get("status") or "")
            for key in ("label", "detail"):
                value = str(payload.get(key) or "").strip()
                if value:
                    line += f" — {value}"
            render.status(line)
            return

        if kind == "agent.plan.updated":
            marks = {"pending": "[ ]", "in_progress": "[~]", "completed": "[x]"}
            lines = ["plan:"]
            for item in payload.get("items") or []:
                mark = marks.get(item.get("status", "pending"), "[ ]")
                lines.append(f"  {mark} {item.get('content', '')}")
            render.plain("\n".join(lines))
            return

        if kind == "agent.context.compacted":
            render.status(
                "context compacted",
                f"{payload.get('tokens_before', '?')} → {payload.get('tokens_after', '?')} tokens",
            )
            return

        if kind == "conversation.created":
            session = payload.get("session") or {}
            sid = session.get("id") if isinstance(session, dict) else None
            if sid:
                render.status("session", str(sid))
            return

        if kind == "error":
            render.error(f"{payload.get('code', 'error')}: {payload.get('message', '')}")
            return

    async def _confirm(self, payload: dict) -> None:
        """Schedule the approval prompt off the engine's await chain.

        Answering synchronously here would race the engine: it reaches
        ``bridge.submit()`` only after ``send_json`` returns, so responding
        early is a no-op and the call would sit out the whole timeout.
        """
        call_id = payload.get("call_id")
        if not call_id:
            return
        result = await ask_user(
            str(payload.get("tool") or "?"),
            payload.get("args") or {},
            f"risk={payload.get('risk')}",
        )
        self.engine.bridge.respond(call_id, result.response)

    async def _confirm_escape(self, payload: dict) -> None:
        """A tool reached for a path outside the workspace. Scheduled off the
        engine's await chain for the same reason as ``_confirm`` — and because
        an unanswered request costs the full 60s timeout and then denies."""
        request_id = payload.get("request_id")
        if not request_id:
            return
        options = [str(o) for o in (payload.get("options") or [])] or ["deny"]
        print()
        print(f"[!] Workspace escape — {payload.get('tool')} wants to "
              f"{payload.get('operation')}")
        print(f"    Target: {payload.get('target_path')}")
        print(f"    Reason: {payload.get('reason')}")
        prompt = f"    {' / '.join(options)} (default {options[0]}) > "
        choice = (
            await asyncio.get_running_loop().run_in_executor(
                None, lambda: input(prompt).strip().lower(),
            )
        ) or options[0]
        self.engine.sandbox_bridge.respond(
            str(request_id), choice if choice in options else options[0],
        )


class FSAR:
    """Interactive CLI front-end for the shared ChatEngine."""

    def __init__(self):
        self.config = get_config()
        self.engine = ChatEngine(self.config, RiskBridge())
        self.sink = _ConsoleSink(self.engine)
        self.running = False
        # Rating prompt toggle (whether to ask for a rating after each reply)
        self._rating_prompt_enabled: bool = bool(
            self.config.get("memory.enable_rating_prompt", True)
        )
        # The /command layer reads the engine's subsystems directly. These are
        # views onto the engine's instances, never separate copies.
        self.tool_registry: ToolRegistry = self.engine.registry
        self.card_repo = self.engine.card_repo
        self.mcp = self.engine.mcp
        self.long_memory = self.engine.long_memory
        self.semantic = self.engine.semantic
        self.user_model = self.engine.user_model
        self.feedback = self.engine.feedback
        self.recall = self.engine.recall
        self.reflection_store = self.engine.reflection_store
        self.decision_log = self.engine.decision_log
        self.reflector = self.engine.idle_reflector

    @property
    def session_id(self) -> str:
        return self.engine.active_conversation_id() or ""

    @property
    def permissions(self) -> PermissionState:
        return self.engine.permissions

    @property
    def risk_engine(self) -> RiskEngine:
        return self.engine.risk_engine

    def _get_llm(self) -> OpenAI:
        return self.engine.client_and_model()[0]

    def start(self):
        self.running = True
        self._print_banner()
        try:
            asyncio.run(self._main())
        except KeyboardInterrupt:
            pass

    async def _main(self):
        # MCP servers and the scheduler come up together inside the event loop
        # so stdio subprocess plumbing works.
        await self.engine.start_mcp()
        if self.mcp.servers:
            n = len(self.mcp.list_visible_tools())
            print(f"  MCP: {len(self.mcp.servers)} server(s) up, {n} tools registered")
        try:
            await self.engine._run_idle_reflection_if_due()
            await self._run_loop()
        finally:
            try:
                await self.engine.stop_mcp()
            except Exception as e:
                logger.warning(f"MCP shutdown error: {e}")

    def _print_banner(self):
        print()
        print("  ███████╗███████╗ █████╗ ██████╗ ")
        print("  ██╔════╝██╔════╝██╔══██╗██╔══██╗")
        print("  █████╗  ███████╗███████║██████╔╝")
        print("  ██╔══╝  ╚════██║██╔══██║██╔══██╗")
        print("  ██║     ███████║██║  ██║██║  ██║")
        print("  ╚═╝     ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝")
        print("  Fully Self-evolving AI Companion")
        print(f"  Session: {self.session_id}")
        print()
        stats = self.long_memory.get_stats()
        if stats["total_messages"] > 0:
            print(f"  Memory: {stats['total_messages']} messages across {stats['total_sessions']} sessions")
        if self.semantic.available:
            n = self.semantic.count()
            if n > 0:
                print(f"  Semantic memory: {n} entries")
        if self.user_model.get_all_preferences():
            print(f"  Preferences: {len(self.user_model.get_all_preferences())} entries")
        if self.user_model.get_profile():
            print(f"  Profile: {len(self.user_model.get_profile())} entries")
        fb = self.feedback.get_stats()
        if fb["total"] > 0:
            print(f"  Ratings: {fb['total']} (avg {fb['avg']})")
        print("  Type /help for commands, /exit to quit")
        print()

    async def _run_loop(self):
        while self.running:
            try:
                user_input = await asyncio.get_event_loop().run_in_executor(None, lambda: input("\nYou > ").strip())
            except (EOFError, KeyboardInterrupt):
                render.warn("Goodbye!")
                break

            if not user_input:
                continue

            if user_input.startswith("/"):
                await self._handle_command(user_input)
            else:
                await self._handle_message(user_input)

    async def _handle_message(self, user_input: str):
        await self.engine.handle_send(self.sink, user_input, "agent")

    def _save_rating_as_fact(self, reason: str, rating: int) -> None:
        """Persist a 1-/2-star correction as a memory_chunk for later recall.

        Low ratings usually mean 'FSAR got X wrong; the truth is Y' — exactly
        the kind of fact the user wants remembered. Without this, the reason
        only surfaces as a behavioral pattern (often too noisy to be useful).
        """
        from src.memory import ExperienceStore
        store = ExperienceStore()
        prefix = "RLHF correction" if rating <= 2 else "User-rated fact"
        title = reason.strip().splitlines()[0][:60]
        for sep in ("。", ".", "!", "?", "！", "？", ";", "；"):
            idx = title.find(sep)
            if idx > 0:
                title = title[:idx]
                break
        title = title.strip() or "correction"
        body = f"{prefix} ({rating}/5): {reason.strip()}"
        store.add_chunk(source="rlhf_correction", title=title, body=body)

    async def _handle_command(self, command: str):
        parts = command.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if cmd == "/exit":
            print("Goodbye!")
            self.running = False
        elif cmd == "/help":
            print("""
Available commands:
  /help                       Show this help
  /exit                       Quit FSAR
  /memory                     Manage memory database (subcommands below)
  /history                    View recent messages in current session
  /search <keyword>           Search memory
  /clear                      Clear current conversation context
  /config                     Show current configuration
  /tools                      List available tools
  /mcp                        MCP server status / reload / add / remove / install / catalog
  /perm                       Permission status / control
  /audit                      View recent audit log
  /rate <n> [reason]          Rate the most recent reply (1-5)
  /profile                    View / edit user profile
  /prefs                      Preferences CRUD
  /feedback                   View rating statistics
  /reflect                    Force immediate reflection
  /stats                      Tool decision-log aggregates (Phase 5.2)
  /embedder                   Show embedding configuration + probe
  /resume [session]           Selectively load a past session
  /exp [view|del|stale|archive] [name]  Phase 6: experiences CRUD
  /learn <name> <cat> "<desc>"          Phase 6: persist a new experience (body from stdin)
  /import <path-to-skill.md>            Phase 6: import external skill markdown
  /remember "<fact>"                    Phase 6: persist a cross-session user fact
  /facts [keyword]                      Phase 6: list / search saved facts
  /skills [status|activity <name> <enable|disable>|delete <name>]  Phase 6: external skills CRUD

Memory management (/memory) subcommands:
  /memory                       Overview (default)
  /memory stats                 Detailed stats (including P3 modules)
  /memory sessions [N]          List most recent N sessions (default 10)
  /memory session <id>          View all messages in a session
  /memory delete <id>           Delete a session (cascades to ratings)
  /memory clear                 Delete all sessions (with confirmation)
  /memory export <file>         Export all sessions to JSON
  /memory search <keyword>      Global keyword search

Permission subcommands:
  /perm                              Show current permission state
  /perm mode <strict|normal|trust>   Switch session mode
  /perm trust <tool>                 Session-scoped trust (lost on restart)
  /perm deny <tool>                  Session-scoped deny (lost on restart)
  /perm grant <tool>                 Permanent trust (writes yaml)
  /perm revoke <tool>                Permanent deny (writes yaml)
  /perm reset                        Reload yaml + clear session-scoped

Profile (/profile) subcommands:
  /profile                         Show profile + preferences + patterns
  /profile set <key> <value>       Set a profile entry
  /profile del <key>               Delete a profile entry

Preferences (/prefs) subcommands:
  /prefs                           Show all preferences
  /prefs set <key> <value>         Set preference (explicit)
  /prefs get <key>                 Look up a preference
  /prefs del <key>                 Delete a preference

Ratings (/feedback):
  /feedback                        Rating stats + high/low samples

Reflection (/reflect):
  /reflect                         Force immediate reflection

Session resume (/resume):
  /resume                          List 20 most recent sessions, pick by number
  /resume <session_id>             Load a specific session directly
  /resume <prefix>                 Match by prefix
""")
        elif cmd == "/memory":
            self._cmd_memory(args)
        elif cmd == "/resume":
            await self._cmd_resume(args)
        elif cmd == "/history":
            rows = self.engine.session_store.get_recent_messages(
                self.session_id, limit=20,
            ) if self.session_id else []
            for msg in rows:
                time_str = msg.timestamp.strftime("%H:%M")
                role = "You" if msg.role == "user" else "FSAR"
                print(f"  [{time_str}] {role}: {msg.content[:80]}")
        elif cmd == "/search":
            results = self.long_memory.search(args, limit=10)
            for r in results:
                print(f"  [{r.timestamp:%Y-%m-%d %H:%M}] {r.role}: {r.content[:60]}")
        elif cmd == "/clear":
            self.engine.clear_short_context()
            print("Conversation context cleared")
        elif cmd == "/config":
            llm = self.config.get_llm_config("primary")
            print(f"LLM: {llm.get('provider')}/{llm.get('model')} @ {llm.get('base_url')}")
        elif cmd == "/tools":
            print("Available tools:")
            for tool in self.tool_registry.list_tools():
                print(f"  - {tool.name}: {tool.description} (risk: {tool.risk_level})")
            if self.mcp.servers:
                print(f"\nMCP servers: {', '.join(self.mcp.servers)}")
                print(f"MCP tools: {len(self.mcp.list_visible_tools())}")
        elif cmd == "/mcp":
            await self._cmd_mcp(args)
        elif cmd == "/mcpadd":
            self._mcp_add_interactive(args)
        elif cmd == "/perm":
            self._cmd_perm(args)
        elif cmd == "/audit":
            self._cmd_audit(args)
        elif cmd == "/rate":
            self._cmd_rate(args)
        elif cmd == "/profile":
            self._cmd_profile(args)
        elif cmd == "/prefs":
            self._cmd_prefs(args)
        elif cmd == "/feedback":
            self._cmd_feedback(args)
        elif cmd == "/reflect":
            self._cmd_reflect(args)
        elif cmd == "/embedder":
            self._cmd_embedder(args)
        elif cmd == "/stats":
            self._cmd_stats(args)
        elif cmd in ("/exp", "/experiences"):
            self._cmd_experiences(args)
        elif cmd == "/learn":
            self._cmd_learn(args)
        elif cmd == "/import":
            self._cmd_import(args)
        elif cmd == "/remember":
            self._cmd_remember(args)
        elif cmd in ("/facts", "/memory_chunks"):
            self._cmd_facts(args)
        elif cmd == "/skills":
            self._cmd_skills(args)
        elif cmd == "/fsar":
            print("00101111 01100001 01110100 01110100 01101001 01100011")
        elif cmd == "/attic":
            print('Traceback (most recent call last):\n'
                  '  File "<stdin>", line 1, in <module>\n'
                  "ModuleNotFoundError: No module named 'src.core.prompt_archive'")
        else:
            print(f"Unknown command: {cmd}")

    def _cmd_experiences(self, args: str) -> None:
        """View / delete experiences. See /learn and /import for adding new ones."""
        from src.memory import ExperienceStore
        store = ExperienceStore()
        parts = args.split()
        if not parts:
            store.render_index()
            exps = store.list_for_index()
            if not exps:
                print("(no experiences yet — use /learn to add one)")
                return
            print("\n[Active Experiences]")
            for e in exps:
                print(f"  [{e.category}] {e.name}: {e.description[:60]} (uses={e.use_count})")
            print(f"\nUse '/exp view <name>' to read body, '/exp del <name>' to delete.")
            return

        sub = parts[0].lower()
        if sub == "view":
            if len(parts) < 2:
                print("Usage: /exp view <name>")
                return
            exp = store.get_by_name(parts[1])
            if not exp:
                print(f"Not found: {parts[1]}")
                return
            store.bump_use(parts[1])
            print(store.render_experience_body(exp))
            return

        if sub == "del":
            if len(parts) < 2:
                print("Usage: /exp del <name>")
                return
            if store.delete_experience(parts[1]):
                print(f"Deleted {parts[1]}")
            else:
                print(f"Not found: {parts[1]}")
            return

        if sub == "stale":
            n = store.mark_stale(days=0)
            print(f"Marked {n} experiences stale (days=0)")
            return

        if sub == "archive":
            n = store.mark_archived(days=0)
            print(f"Archived {n} experiences (days=0)")
            return

        print("Usage: /exp | /exp view <name> | /exp del <name> | /exp stale | /exp archive")

    def _cmd_learn(self, args: str) -> None:
        """Persist an experience from CLI. Reads body from stdin until EOF/blank line.

        Format expected after '/learn':  NAME  CATEGORY  "DESCRIPTION"
        Then body lines until a blank line is entered.
        """
        from src.memory import ExperienceStore, Experience
        from datetime import datetime
        parts = args.split()
        if len(parts) < 3:
            print('Usage: /learn <name> <category> "<description up to 60 chars>"')
            print('Then type the procedure body, finish with a blank line.')
            return
        name = parts[0]
        category = parts[1]
        description = " ".join(parts[2:]).strip().strip('"')[:60]
        print("(Enter procedure body, end with a blank line or Ctrl+D/Ctrl+Z)")
        body_lines: list[str] = []
        while True:
            try:
                line = input()
            except EOFError:
                break
            if line.strip() == "":
                break
            body_lines.append(line)
        body = "\n".join(body_lines).strip()
        if not body:
            print("Cancelled (empty body).")
            return
        store = ExperienceStore()
        existing = store.get_by_name(name)
        now = datetime.now().isoformat(timespec="seconds")
        exp = Experience(
            name=name, category=category, description=description, body=body,
            created_by="user", created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        eid = store.upsert_experience(exp)
        op = "updated" if existing else "created"
        print(f"[OK] Experience {op}: id={eid} name='{name}' category='{category}'")
        print(f"      description: {description}")
        print(f"      body: {len(body)} chars")

    def _cmd_skills(self, args: str) -> None:
        """List / enable / disable external-skill experience rows."""
        from src.memory import ExperienceStore, STATE_ACTIVE, STATE_ARCHIVED
        parts = args.split()
        sub = parts[0].lower() if parts else "status"

        if sub == "status":
            store = ExperienceStore()
            exps = store.list_for_index(
                categories=["external-skill"],
                include_states=["active", "stale", "archived"],
            )
            if not exps:
                print("(no external skills installed — install one or run /learn)")
                return
            print(f"\n[External Skills] {len(exps)}")
            counts = {"active": 0, "stale": 0, "archived": 0}
            for e in exps:
                counts[e.state] = counts.get(e.state, 0) + 1
                tag = "ENABLED " if e.state == "active" else (f"{e.state.upper():9s}")
                print(f"  [{tag}] {e.name}: {e.description[:60]} (uses={e.use_count})")
            print(f"\nTotal: active={counts.get('active',0)} stale={counts.get('stale',0)} archived={counts.get('archived',0)}")
            print(f"Use '/skills activity <name> enable|disable' to toggle.")
            return

        if sub == "activity" and len(parts) >= 3:
            store = ExperienceStore()
            name = parts[1]
            action = parts[2].lower()
            if action in ("enable", "on", "active"):
                if store.set_state(name, STATE_ACTIVE):
                    print(f"[OK] Enabled: {name}")
                else:
                    print(f"[NOT_FOUND] {name}")
                return
            if action in ("disable", "off", "archived"):
                if store.set_state(name, STATE_ARCHIVED):
                    print(f"[OK] Disabled: {name}")
                else:
                    print(f"[NOT_FOUND] {name}")
                return
            print(f"Unknown action: {action!r}")
            return

        if sub == "delete" and len(parts) >= 2:
            store = ExperienceStore()
            name = parts[1]
            if store.delete_experience(name):
                print(f"[OK] Deleted: {name}")
            else:
                print(f"[NOT_FOUND] {name}")
            return

        print("Usage: /skills status | /skills activity <name> enable|disable | /skills delete <name>")

    def _cmd_import(self, args: str) -> None:
        """Import an external .md skill into the experience layer."""
        from pathlib import Path
        from src.tools.builtin.experience_import import import_markdown_file
        path = args.strip()
        if not path:
            print("Usage: /import <path-to-skill.md>")
            return
        try:
            res = import_markdown_file(Path(path))
        except Exception as e:
            print(f"[ERROR] {e}")
            return
        if res is None:
            return
        name, action, fields = res
        print(f"[OK] {action} '{name}'")
        for k, v in fields.items():
            if v:
                print(f"      {k}: {v[:80]}")

    def _cmd_remember(self, args: str) -> None:
        """Persist a cross-session fact."""
        from src.memory import ExperienceStore
        text = args.strip()
        if not text:
            print('Usage: /remember "<the fact to remember>"')
            print('Example: /remember "我家猫叫贝贝"')
            return
        store = ExperienceStore()
        title = text.splitlines()[0]
        for sep in ("。", ".", "!", "?", "！", "？"):
            idx = title.find(sep)
            if idx > 0:
                title = title[:idx]
                break
        title = title.strip()[:60] or "fact"
        cid = store.add_chunk(source="user_fact", title=title, body=text)
        print(f"[OK] Saved fact #{cid}: {title}")
        print(f"      {text[:120]}")

    def _cmd_facts(self, args: str) -> None:
        """List or search saved facts (memory_chunks)."""
        from src.memory import ExperienceStore
        store = ExperienceStore()
        keyword = args.strip()
        if keyword:
            hits = store.search_chunks(keyword, limit=10)
            if not hits:
                print(f"No facts match: {keyword!r}")
                return
            print(f"\nFacts matching {keyword!r}:")
            for c in hits:
                print(f"  [{c.id}] {c.title}: {c.body[:100]}")
        else:
            chunks = store.list_chunks(source="user_fact", limit=50)
            if not chunks:
                print("(no saved facts yet — try /remember \"something\" )")
                return
            print(f"\nSaved facts ({len(chunks)}):")
            for c in chunks:
                print(f"  [{c.id}] {c.title}")
                print(f"      {c.body[:100]}")

    def _cmd_perm(self, args: str) -> None:
        """Permission control — mode / trust / deny / grant / revoke / reset."""
        parts = args.split()
        sub = parts[0].lower() if parts else ""

        if sub == "":
            # Show current state
            print(f"mode: {self.permissions.mode}")
            print(f"session_trust: {sorted(self.permissions.session_trust) or '(none)'}")
            print(f"session_deny:  {sorted(self.permissions.session_deny) or '(none)'}")
            print(f"\nTool policies:")
            for name, cfg in self.permissions.tools.items():
                if "operations" in cfg:
                    ops = ", ".join(f"{k}={v}" for k, v in cfg["operations"].items())
                    print(f"  {name}: [risk={cfg.get('risk','?')}] {ops}")
                else:
                    blocked = cfg.get("blocked_patterns", [])
                    print(f"  {name}: [risk={cfg.get('risk','?')}] mode={cfg.get('mode','ask')}"
                          + (f" blocked={blocked}" if blocked else ""))
            return

        if sub == "mode":
            new = parts[1].lower() if len(parts) > 1 else ""
            if new not in ("strict", "normal", "trust"):
                print("Usage: /perm mode <strict|normal|trust>")
                return
            self.permissions.mode = new
            print(f"Mode switched to: {new}")
            return

        if sub in ("trust", "deny"):
            if len(parts) < 2:
                print(f"Usage: /perm {sub} <tool_name>")
                return
            tool_name = parts[1]
            if sub == "trust":
                self.permissions.set_session_trust(tool_name)
                print(f"✓ Session-scoped trust granted to {tool_name} (lost on restart)")
            else:
                self.permissions.set_session_deny(tool_name)
                print(f"✓ Session-scoped deny set for {tool_name} (lost on restart)")
            return

        if sub in ("grant", "revoke"):
            if len(parts) < 2:
                print(f"Usage: /perm {sub} <tool_name>")
                return
            tool_name = parts[1]
            if sub == "grant":
                self.permissions.set_permanent_trust(tool_name)
            else:
                self.permissions.set_permanent_deny(tool_name)
            save_permissions(self.permissions)
            print(f"✓ Wrote back to permissions.yaml")
            return

        if sub == "reset":
            self.engine.permissions = load_permissions()
            self.engine.risk_engine = RiskEngine(self.engine.permissions)
            print(f"✓ Reloaded permissions.yaml")
            return

        print(f"Unknown subcommand: {sub} (try /perm to see options)")

    async def _cmd_mcp(self, args: str) -> None:
        """MCP server management — status / reload / add / remove / list / install / catalog."""
        parts = args.split()
        sub = parts[0].lower() if parts else "status"

        if sub == "status":
            print(f"\n[MCP Status]")
            print(f"  Config: {self.mcp._config_path}")
            print(f"  Servers: {len(self.mcp.servers)}")
            for s in self.mcp.servers:
                client = self.mcp.get_client(s)
                info = client.server_info if client else {}
                started = "OK" if (client and client.started) else "FAIL"
                print(f"    [{started}] {s}: {info.get('name', '?')} v{info.get('version', '?')}")
            print(f"  Registered tools: {len(self.mcp.list_visible_tools())}")
            for t in self.mcp.list_visible_tools():
                print(f"    - {t.name} (risk={t.risk_level})")
            return

        if sub == "reload":
            print("Reloading MCP config...")
            try:
                await self.mcp.reload()
                n = len(self.mcp.list_visible_tools())
                print(f"  OK: {len(self.mcp.servers)} server(s), {n} tools")
            except Exception as e:
                render.warn(f"Reload failed: {e}")
            return

        if sub == "add":
            self._mcp_add_interactive(args[len("add"):].strip())
            return

        if sub == "remove":
            self._mcp_remove_interactive(args[len("remove"):].strip())
            return

        if sub == "list":
            self._mcp_list_interactive()
            return

        if sub == "install" or sub == "i":
            self._mcp_install_interactive(args[len(sub):].strip())
            return

        if sub == "catalog":
            self._mcp_show_catalog()
            return

        print(f"Usage: /mcp [status | reload | add | remove | list | install | catalog]")

    def _mcp_list_interactive(self) -> None:
        """Show all configured MCP servers (from .env / YAML, not just running ones)."""
        from src.mcp import cli as mcpcli
        env_path = self.mcp._config_path.parent.parent / ".env"  # best-effort
        # Prefer the real .env next to settings.yaml
        candidates = [
            Path.cwd() / ".env",
            Path(__file__).resolve().parent / ".env",
        ]
        env_path = next((p for p in candidates if p.is_file()), candidates[0])
        servers = mcpcli._read_servers(env_path if env_path.is_file() else None)
        if not servers:
            print("(no MCP servers configured)")
            print(f"  source: {env_path}")
            return
        print(f"source: {env_path}")
        for s in servers:
            name = s.get("name", "?")
            cmd = s.get("command", "?")
            cmd_args = " ".join(s.get("args") or [])
            risk = s.get("risk_level", "HIGH")
            enabled = "ON " if s.get("enabled", False) else "off"
            print(f"  [{enabled}] {name} ({risk}): {cmd} {cmd_args}".rstrip())

    def _mcp_add_interactive(self, rest: str) -> None:
        """Parse `/mcp add <name> --command X [--arg A --arg B]` and persist.

        Supports both --arg (repeatable) and --args 'JSON' forms. Writes the
        update to .env immediately; offers to reload.
        """
        from src.mcp import cli as mcpcli
        import shlex
        try:
            tokens = shlex.split(rest) if rest else []
        except ValueError as e:
            render.warn(f"Failed to parse arguments: {e}")
            return
        if not tokens or tokens[0].startswith("-"):
            print("Usage: /mcp add <name> --command <cmd> [--arg X ...] [--args 'JSON'] [--risk LEVEL]")
            print("   or: /mcp add <name> --snippet  (print JSON snippet)")
            return

        name = tokens[0]
        # Build an argparse namespace off a fake argv
        import argparse
        parser = argparse.ArgumentParser(prog="add", add_help=False)
        parser.add_argument("--command")
        parser.add_argument("--arg", action="append", default=[])
        parser.add_argument("--args", dest="args_json", default=None)
        parser.add_argument("--risk")
        parser.add_argument("--disabled", action="store_true")
        parser.add_argument("--snippet", action="store_true")
        try:
            ns = parser.parse_args(tokens[1:])
        except SystemExit:
            return

        if ns.snippet:
            # Print a single-server snippet instead of writing
            server = {"name": name, "command": ns.command or "?"}
            if ns.arg:
                server["args"] = ns.arg
            if ns.args_json:
                try:
                    server["args"] = json.loads(ns.args_json)
                except json.JSONDecodeError as e:
                    render.warn(f"--args is not valid JSON: {e}")
                    return
            if ns.risk:
                server["risk_level"] = ns.risk.upper()
            server["enabled"] = not ns.disabled
            print(json.dumps(server, ensure_ascii=False))
            return

        if not ns.command:
            render.warn("Missing --command")
            return

        server = {"name": name, "command": ns.command}
        if ns.arg or ns.args_json:
            args_list = list(ns.arg)
            if ns.args_json:
                try:
                    extra = json.loads(ns.args_json)
                except json.JSONDecodeError as e:
                    render.warn(f"--args is not valid JSON: {e}")
                    return
                if not isinstance(extra, list):
                    render.warn("--args must be a JSON array")
                    return
                args_list.extend(str(x) for x in extra)
            server["args"] = args_list
        if ns.risk:
            server["risk_level"] = ns.risk.upper()
        server["enabled"] = not ns.disabled

        env_path = self._find_env_file()
        if not env_path.is_file():
            print(f"Will create: {env_path}")

        servers = mcpcli._read_servers(env_path if env_path.is_file() else None)
        servers = mcpcli._upsert(servers, server)
        new_value = json.dumps(servers, ensure_ascii=False)
        mcpcli.write_env_block(env_path, "MCP_SERVERS", new_value)

        render.ok(f"Added '{name}' to {env_path}")
        print(f"  Restart FSAR or run /mcp reload to activate.")

    def _mcp_remove_interactive(self, rest: str) -> None:
        from src.mcp import cli as mcpcli
        name = rest.strip()
        if not name:
            print("Usage: /mcp remove <name>")
            return
        env_path = self._find_env_file()
        servers = mcpcli._read_servers(env_path if env_path.is_file() else None)
        if not any(s.get("name") == name for s in servers):
            render.warn(f"'{name}' is not in the config")
            return
        filtered = [s for s in servers if s.get("name") != name]
        if filtered:
            mcpcli.write_env_block(env_path, "MCP_SERVERS", json.dumps(filtered, ensure_ascii=False))
        else:
            mcpcli.remove_env_block(env_path, "MCP_SERVERS")
        render.ok(f"Removed '{name}'")

    def _find_env_file(self) -> Path:
        from src.mcp.cli import find_env_file
        return find_env_file()

    def _mcp_show_catalog(self) -> None:
        """Print the preset catalog (one line per preset)."""
        from src.mcp.presets import list_presets
        print(f"\n[MCP Server Catalog]")
        for i, (key, preset) in enumerate(list_presets(), 1):
            print(f"  {i}. {key} ({preset['risk_level']})")
            print(f"     {preset['description']}")
        print(f"\n  c. custom (enter the command by hand)")
        print(f"\n  Type a number / name to install; q to quit.")

    def _mcp_install_interactive(self, rest: str) -> None:
        """Interactive MCP installer. Picks from catalog or accepts custom input.

        Args after `install` are optional and can pre-select a preset:
            /mcp install                  → show catalog and prompt
            /mcp install filesystem       → install filesystem preset
            /mcp install filesystem --path C:/foo  → preset + placeholder values
        """
        from src.mcp.presets import MCP_PRESETS, fill_placeholders, get_preset
        from src.mcp import cli as mcpcli

        parts = rest.split() if rest else []
        chosen_key: str | None = None
        provided_values: dict[str, str] = {}

        if parts:
            # Direct selection: /mcp install filesystem ...
            chosen_key = parts[0]
            # Pre-look up the preset so we can map short flags -> tokens
            preset_for_flags = get_preset(chosen_key) if chosen_key else None
            flag_to_token: dict[str, str] = {}
            if preset_for_flags:
                for ph in preset_for_flags.get("placeholders", []):
                    if ph.get("flag"):
                        flag_to_token[ph["flag"]] = ph["token"]
            # Parse --flag value pairs (e.g., --path C:/foo)
            i = 1
            while i < len(parts):
                tok = parts[i]
                if tok.startswith("--") and i + 1 < len(parts):
                    flag = tok[2:]
                    if flag in flag_to_token:
                        provided_values[flag_to_token[flag]] = parts[i + 1]
                    else:
                        # Fallback: try <FLAG_NAME> as literal token
                        provided_values[f"<{flag.upper()}>"] = parts[i + 1]
                    i += 2
                else:
                    i += 1
        else:
            # Show catalog, prompt user
            self._mcp_show_catalog()
            try:
                choice = input("\nPick one (number/name, c=custom, q=quit): ").strip()
            except (EOFError, KeyboardInterrupt):
                return
            if not choice or choice.lower() == "q":
                return
            if choice.lower() == "c":
                chosen_key = None  # custom path
            elif choice.isdigit():
                presets = list(MCP_PRESETS.items())
                idx = int(choice) - 1
                if 0 <= idx < len(presets):
                    chosen_key = presets[idx][0]
                else:
                    render.warn(f"Number out of range")
                    return
            else:
                if choice in MCP_PRESETS:
                    chosen_key = choice
                else:
                    render.warn(f"Unknown preset: {choice}")
                    return

        if chosen_key is not None:
            preset = get_preset(chosen_key)
            if preset is None:
                render.warn(f"Unknown preset: {chosen_key}")
                return
            server = self._prompt_preset_placeholders(chosen_key, preset, provided_values)
            if server is None:
                return  # user cancelled
        else:
            server = self._prompt_custom_server()
            if server is None:
                return

        # Write to .env
        env_path = self._find_env_file()
        if not env_path.is_file():
            print(f"Will create: {env_path}")
        servers = mcpcli._read_servers(env_path if env_path.is_file() else None)
        servers = mcpcli._upsert(servers, server)
        new_value = json.dumps(servers, ensure_ascii=False)
        mcpcli.write_env_block(env_path, "MCP_SERVERS", new_value)
        render.ok(f"Wrote '{server['name']}' to {env_path}")
        print(f"  Next: run /mcp reload to activate, or restart FSAR")

    def _prompt_preset_placeholders(
        self, name: str, preset: dict, provided: dict[str, str]
    ) -> dict | None:
        """Fill <TOKEN> placeholders for a preset, prompting if missing."""
        from src.mcp.presets import fill_placeholders
        values: dict[str, str] = {}
        import os

        for ph in preset.get("placeholders", []):
            token = ph["token"]
            if token in provided:
                values[token] = provided[token]
                continue
            default = ph.get("default", "")
            # Expand ${ENV_VAR} in default
            if default.startswith("${") and default.endswith("}"):
                env_name = default[2:-1]
                default = os.environ.get(env_name, "")
            prompt = ph.get("prompt", token)
            if default:
                prompt = f"{prompt} [{default}]"
            prompt = f"{prompt}: "
            try:
                raw = input(prompt).strip()
            except (EOFError, KeyboardInterrupt):
                print("\nCancelled.")
                return None
            value = raw or default
            if not value:
                render.warn(f"{token} cannot be empty, cancelled.")
                return None
            values[token] = value

        out = fill_placeholders(preset, values)
        return {
            "name": name,
            "command": out["command"],
            "args": out.get("args", []),
            "risk_level": out.get("risk_level", "HIGH"),
            "enabled": True,
        }

    def _prompt_custom_server(self) -> dict | None:
        """Step-by-step custom server entry."""
        try:
            name = input("Short name (English, e.g. 'cua'): ").strip()
            if not name:
                print("Cancelled.")
                return None
            command = input("Launch command (e.g. npx / python / cua-mcp-server): ").strip()
            if not command:
                print("Cancelled.")
                return None
            args_raw = input("Args (space-separated; quote values starting with -): ").strip()
            risk_raw = input("Risk level SAFE/LOW/MEDIUM/HIGH/CRITICAL [HIGH]: ").strip().upper()
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.")
            return None

        risk = risk_raw or "HIGH"
        if risk not in {"SAFE", "LOW", "MEDIUM", "HIGH", "CRITICAL"}:
            render.warn(f"Unknown risk level {risk!r}, using HIGH.")
            risk = "HIGH"

        # Tokenize args with shlex so quotes work
        import shlex
        try:
            args = shlex.split(args_raw) if args_raw else []
        except ValueError as e:
            render.warn(f"Failed to parse args: {e}")
            return None

        return {
            "name": name,
            "command": command,
            "args": args,
            "risk_level": risk,
            "enabled": True,
        }

    def _cmd_audit(self, args: str) -> None:
        """Audit log viewer — /audit | /audit N | /audit tail."""
        from src.security import tail as audit_tail
        parts = args.split()
        if not parts:
            n = 10
        elif parts[0] == "tail":
            n = 20
        else:
            try:
                n = int(parts[0])
            except ValueError:
                print(f"Usage: /audit [N|tail] (default 10)")
                return

        entries = audit_tail(n)
        if not entries:
            print("(audit log is empty)")
            return

        print(f"Most recent {len(entries)} entries:")
        for e in entries:
            outcome = e.get("outcome", "?")
            err = f" err={e.get('error')}" if e.get("error") else ""
            args_preview = ", ".join(f"{k}={repr(str(v)[:50])}" for k, v in (e.get("args") or {}).items())
            print(f"  [{e['ts']}] {e['tool']} verdict={e['verdict']}"
                  f" user={e.get('user_response','')} outcome={outcome}{err}")
            if args_preview:
                print(f"      args: {args_preview[:160]}")

    # ---------- P3 command implementations ----------

    def _cmd_rate(self, args: str) -> None:
        """Rate the most recent assistant reply (1-5), with optional reason."""
        parts = args.split(maxsplit=1)
        if not parts:
            print("Usage: /rate <1-5> [reason]")
            return
        try:
            rating = int(parts[0])
        except ValueError:
            print(f"Rating must be an integer 1-5, got: {parts[0]!r}")
            return
        if not (1 <= rating <= 5):
            print("Rating must be 1-5")
            return
        reason = parts[1] if len(parts) > 1 else ""

        # The engine owns the reply→row-id map; the newest entry is the reply
        # the user is looking at.
        last: int | None = None
        for value in self.engine._msg_ids.values():
            last = value
        if last is None:
            print("No reply to rate yet (start a conversation first).")
            return

        try:
            self.feedback.add_or_update_rating(
                message_id=last,
                session_id=self.session_id,
                rating=rating,
                reason=reason,
            )
            if reason:
                tag = "positive" if rating >= 4 else ("negative" if rating <= 2 else "neutral")
                self.user_model.record_pattern(
                    f"User {tag} feedback: {reason[:60]}",
                    f"Rated {rating}/5, reason: {reason}",
                )
                # RLHF correction → long-term memory. Survives across sessions
                # so future asks "what did the user correct me on?" can recall it.
                try:
                    self._save_rating_as_fact(reason, rating)
                except Exception as e:
                    logger.debug(f"rate-reason→memory_chunk skipped: {e}")
            render.ok(f"Rated msg#{last} {rating}/5"
                      + (f" — {reason}" if reason else ""))
        except Exception as e:
            render.warn(f"Failed to record rating: {e}")

    def _cmd_profile(self, args: str) -> None:
        """View / edit user profile."""
        parts = args.split(maxsplit=2)
        if not parts:
            profile = self.user_model.get_profile()
            prefs = self.user_model.get_all_preferences()
            patterns = self.user_model.get_top_patterns(limit=10)

            print("\n[User Profile]")
            if profile:
                for k, v in profile.items():
                    print(f"  - {k}: {v}")
            else:
                print("  (empty — run /reflect to generate)")
            print(f"\n[Preferences] ({len(prefs)} entries)")
            for k, p in prefs.items():
                src = f"[{p.source}]" if p.source != "explicit" else ""
                print(f"  - {k} = {p.value} {src}")
            print(f"\n[Behavioral Patterns] ({len(patterns)} entries)")
            for p in patterns:
                print(f"  - {p['pattern']} (x{p['count']})")
            return

        if parts[0] == "set" and len(parts) >= 3:
            key, value = parts[1], parts[2]
            self.user_model.set_profile(key, value, source="manual")
            render.ok(f"Profile updated: {key} = {value}")
            return

        if parts[0] == "del" and len(parts) >= 2:
            if self.user_model.delete_profile(parts[1]):
                render.ok(f"Profile entry deleted: {parts[1]}")
            else:
                render.warn(f"Profile entry not found: {parts[1]}")
            return

        print("Usage: /profile  |  /profile set <k> <v>  |  /profile del <k>")

    def _cmd_prefs(self, args: str) -> None:
        """Preferences CRUD."""
        parts = args.split()
        if not parts:
            prefs = self.user_model.get_all_preferences()
            print(f"Preferences ({len(prefs)} entries):")
            for k, p in prefs.items():
                src = f"[{p.source}]" if p.source != "explicit" else ""
                print(f"  - {k} = {p.value} {src}")
            return

        sub = parts[0]
        if sub == "set" and len(parts) >= 3:
            self.user_model.set_preference(parts[1], parts[2], source="explicit")
            render.ok(f"Preference set: {parts[1]} = {parts[2]}")
        elif sub == "del" and len(parts) >= 2:
            # Soft-delete by overwriting with empty value + source='deleted' marker
            # (SQLite has no DELETE here; sentinel avoids losing history)
            self.user_model.set_preference(parts[1], "", source="deleted")
            render.ok(f"Preference marked deleted: {parts[1]} (overwritten with empty)")
        elif sub == "get" and len(parts) >= 2:
            v = self.user_model.get_preference(parts[1])
            print(f"{parts[1]} = {v!r}" if v is not None else f"{parts[1]} does not exist")
        else:
            print("Usage: /prefs [set <k> <v> | get <k> | del <k>]")

    def _cmd_feedback(self, args: str) -> None:
        """Rating statistics + recent high/low samples."""
        stats = self.feedback.get_stats()
        print(f"\n[Rating Statistics]")
        print(f"  Total: {stats['total']}")
        print(f"  Average: {stats['avg']}")
        print(f"  High (>=4): {stats['high_count']}")
        print(f"  Low  (<=2): {stats['low_count']}")

        low = self.feedback.get_low_rated(limit=5)
        if low:
            print(f"\n[Low-rated samples]")
            for s in low:
                reason = f" — {s['reason']}" if s.get("reason") else ""
                print(f"  [{s['timestamp'][:16]}] {s['rating']}/5{reason}: {s['content'][:80]}")

        high = self.feedback.get_high_rated(limit=3)
        if high:
            print(f"\n[High-rated samples]")
            for s in high:
                reason = f" — {s['reason']}" if s.get("reason") else ""
                print(f"  [{s['timestamp'][:16]}] {s['rating']}/5{reason}: {s['content'][:80]}")

    def _cmd_reflect(self, args: str) -> None:
        """Force an immediate reflection pass."""
        print("Reflecting...")
        # Inject LLM
        if self.reflector._llm is None:
            try:
                self.reflector.set_llm(self._get_llm())
            except Exception as e:
                logger.warning(f"Cannot init LLM for reflection: {e}")

        try:
            report = self.reflector.reflect(force=True)
            if report is None:
                render.warn("Reflection produced no report (not enough data?)")
                return
            print(f"\nReflection complete:")
            if report.profile:
                print(f"  Profile ({len(report.profile)}):")
                for k, v in report.profile.items():
                    print(f"    - {k}: {v}")
            if report.preferences:
                print(f"  Preferences ({len(report.preferences)}):")
                for k, v in report.preferences.items():
                    print(f"    - {k} = {v}")
            if report.patterns:
                print(f"  Patterns ({len(report.patterns)}):")
                for p in report.patterns:
                    print(f"    - {p['pattern']}")
        except Exception as e:
            render.warn(f"Reflection failed: {e}")

    def _cmd_memory(self, args: str) -> None:
        """Memory database management — stats / sessions / session / delete / clear / export / search."""
        parts = args.split()
        if not parts:
            self._memory_overview()
            return
        sub = parts[0].lower()
        rest = parts[1:]

        if sub == "stats":
            self._memory_overview(detailed=True)
        elif sub == "sessions":
            n = int(rest[0]) if rest else 10
            self._memory_list_sessions(n)
        elif sub == "session":
            if not rest:
                print("Usage: /memory session <session_id>")
                return
            self._memory_view_session(rest[0])
        elif sub == "delete":
            if not rest:
                print("Usage: /memory delete <session_id>")
                return
            self._memory_delete_session(rest[0])
        elif sub == "clear":
            self._memory_clear_all()
        elif sub == "export":
            if not rest:
                print("Usage: /memory export <file.json>")
                return
            self._memory_export(rest[0])
        elif sub == "search":
            if not rest:
                print("Usage: /memory search <keyword>")
                return
            self._memory_search(" ".join(rest))
        else:
            print("Usage: /memory [stats | sessions [N] | session <id> | delete <id> "
                  "| clear | export <file> | search <kw>]")

    def _memory_overview(self, detailed: bool = False) -> None:
        stats = self.recall.stats()
        print("\n[Memory System Overview]")
        print(f"  Sessions: {stats['long_term']['total_sessions']}")
        print(f"  Messages: {stats['long_term']['total_messages']}")
        print(f"  Semantic: {stats['semantic_count']} (chroma available: {stats['semantic_available']})")
        print(f"  Preferences: {stats['preferences_count']}")
        print(f"  Patterns: {stats['patterns_count']}")
        print(f"  Profile: {stats['profile_count']}")
        fb = stats['feedback']
        print(f"  Ratings: {fb['total']} (avg={fb['avg']}, "
              f"high>=4: {fb['high_count']}, low<=2: {fb['low_count']})")
        print(f"  Current session: {self.session_id} ({len(self.engine.short_context())} context messages)")

        if detailed:
            print("\n[Recent Sessions]")
            sessions = self.long_memory.list_sessions_with_count(limit=5)
            for s in sessions:
                marker = " <- current" if s["session_id"] == self.session_id else ""
                print(f"  - {s['session_id']}  ({s['count']} msgs)  "
                      f"{s['first_ts'][:16]} -> {s['last_ts'][:16]}{marker}")

    def _memory_list_sessions(self, n: int) -> None:
        sessions = self.long_memory.list_sessions_with_count(limit=n)
        if not sessions:
            print("(no past sessions)")
            return
        print(f"\nMost recent {len(sessions)} sessions:")
        print(f"  {'#':<4} {'session_id':<14} {'msgs':<6} {'first':<17} {'last':<17}")
        for i, s in enumerate(sessions, 1):
            marker = " *" if s["session_id"] == self.session_id else "  "
            print(f"  {i:<2}{marker} {s['session_id']:<14} {s['count']:<6} "
                  f"{s['first_ts'][:16]:<17} {s['last_ts'][:16]:<17}")

    def _memory_view_session(self, session_id: str) -> None:
        # Prefix matching
        actual = self._resolve_session_id(session_id)
        if not actual:
            return
        msgs = self.long_memory.get_session_messages(actual)
        if not msgs:
            print(f"Session {actual} is empty")
            return
        print(f"\nSession {actual} ({len(msgs)} messages):")
        print(f"  {'time':<17} {'role':<10} {'content':<60}")
        print(f"  {'-'*17} {'-'*10} {'-'*60}")
        for m in msgs:
            content = m.content[:60].replace("\n", " ")
            print(f"  {m.timestamp.strftime('%Y-%m-%d %H:%M'):<17} "
                  f"{m.role:<10} {content}")

    def _memory_delete_session(self, session_id: str) -> None:
        actual = self._resolve_session_id(session_id)
        if not actual:
            return
        if actual == self.session_id:
            render.warn("Cannot delete the active session (use /exit or /resume another one first)")
            return
        n = self.long_memory.delete_session(actual)
        render.ok(f"Deleted session {actual} ({n} messages, ratings cascaded)")

    def _memory_clear_all(self) -> None:
        sessions = self.long_memory.list_sessions_with_count(limit=10**9)
        total_msgs = sum(s["count"] for s in sessions)
        print(f"\n[!] About to clear {len(sessions)} sessions, {total_msgs} messages (irreversible)")
        confirm = input("   Confirm deletion? Type 'yes' to continue: ").strip().lower()
        if confirm != "yes":
            print("   Cancelled.")
            return
        deleted = 0
        for s in sessions:
            if s["session_id"] == self.session_id:
                continue
            deleted += self.long_memory.delete_session(s["session_id"])
        render.ok(f"Deleted {deleted} messages (current session {self.session_id} preserved)")

    def _memory_export(self, path: str) -> None:
        from pathlib import Path
        out = Path(path)
        if not out.is_absolute():
            out = Path("data") / out
        try:
            data = self.long_memory.export_all()
            out.parent.mkdir(parents=True, exist_ok=True)
            import json as _json
            with open(out, "w", encoding="utf-8") as f:
                _json.dump(data, f, ensure_ascii=False, indent=2)
            render.ok(f"Exported to {out} "
                      f"({data['total_sessions']} sessions, "
                      f"{sum(s['count'] for s in data['sessions'])} messages)")
        except Exception as e:
            render.warn(f"Export failed: {e}")

    def _memory_search(self, keyword: str) -> None:
        results = self.long_memory.search(keyword, limit=20)
        if not results:
            print(f"No matches: {keyword!r}")
            return
        print(f"\nSearch results for {keyword!r} ({len(results)} hits):")
        for r in results:
            content = r.content[:80].replace("\n", " ")
            print(f"  [{r.timestamp.strftime('%Y-%m-%d %H:%M')}] "
                  f"{r.session_id}/{r.role}: {content}")

    def _resolve_session_id(self, sid: str) -> str | None:
        """Support full ID or prefix matching."""
        sessions = self.long_memory.get_sessions()
        if not sessions:
            print("(no past sessions)")
            return None
        matches = [s for s in sessions if s == sid or s.startswith(sid)]
        if not matches:
            print(f"Session not found: {sid!r} (try /memory sessions for the list)")
            return None
        if len(matches) > 1:
            print(f"Prefix {sid!r} matches {len(matches)} sessions: {matches[:5]}")
            return None
        return matches[0]

    async def _cmd_resume(self, args: str) -> None:
        """Selectively load a past session into current context."""
        loop = asyncio.get_event_loop()
        parts = args.split()

        if not parts:
            # List most recent 20 sessions for the user to choose from
            sessions = self.long_memory.list_sessions_with_count(limit=20)
            if not sessions:
                print("(no past sessions)")
                return
            print("\nPast sessions (enter a number to load):")
            print(f"  {'#':<4} {'session_id':<14} {'msgs':<6} {'last':<17}")
            for i, s in enumerate(sessions, 1):
                marker = " *" if s["session_id"] == self.session_id else "  "
                print(f"  {i:<2}{marker} {s['session_id']:<14} {s['count']:<6} "
                      f"{s['last_ts'][:16]:<17}")
            try:
                raw = input("\n  Pick a # (or session_id, Enter to cancel): ").strip()
            except (EOFError, KeyboardInterrupt):
                return
            if not raw:
                return
            try:
                idx = int(raw)
                if 1 <= idx <= len(sessions):
                    sid = sessions[idx - 1]["session_id"]
                else:
                    print(f"Number out of range")
                    return
            except ValueError:
                sid = self._resolve_session_id(raw)
                if not sid:
                    return
        else:
            sid = self._resolve_session_id(parts[0])
            if not sid:
                return

        # Load into the engine's active conversation
        msgs = self.long_memory.get_session_messages(sid)
        if not msgs:
            print(f"Session {sid} is empty")
            return

        old_sid = self.session_id
        await self.engine.switch_conversation(sid)

        print(f"\nResumed session {sid} ({len(msgs)} messages loaded into context)")
        print(f"  Previous session {old_sid} is paused; new messages will write to {sid}")
        # Print the last few messages for context
        print(f"\n  Recent message preview:")
        for m in msgs[-3:]:
            content = m.content[:60].replace("\n", " ")
            print(f"    [{m.role}] {content}")

    def _cmd_stats(self, args: str) -> None:
        """Tool decision-log aggregates (Phase 5.2) + recent task reflections."""
        parts = args.split()
        sub = parts[0].lower() if parts else ""

        if sub == "recent":
            try:
                limit = int(parts[1]) if len(parts) > 1 else 10
            except ValueError:
                limit = 10
            recent = self.reflection_store.list_recent(limit=limit,
                                                       session_id=self.session_id
                                                       if "session" in (parts[2:] if len(parts) > 2 else [])
                                                       else None)
            if not recent:
                print("(no task reflections yet)")
                return
            print(f"\nMost recent {len(recent)} task reflections:")
            for r in recent:
                print(f"\n  [{r['created_at'][:16]}] task={r['task_id'][:20]} outcome={r['outcome']}")
                print(f"    steps={r['step_count']} errors={r['error_count']} tools={','.join(r['tools_used'][:3])}")
                if r['failure_modes']:
                    print(f"    failures: {'; '.join(r['failure_modes'][:2])[:120]}")
                if r['suggested_strategy']:
                    print(f"    strategy: {r['suggested_strategy'][:120]}")
            return

        if sub == "tool":
            tool_name = parts[1] if len(parts) > 1 else ""
            if not tool_name:
                print("Usage: /stats tool <name>")
                return
            with self.decision_log._connect() as conn:
                rows = conn.execute("""
                    SELECT step_no, args_summary, latency_ms, success,
                           error_class, created_at
                    FROM decision_log
                    WHERE chosen_tool = ?
                    ORDER BY created_at DESC LIMIT 10
                """, (tool_name,)).fetchall()
            if not rows:
                print(f"(no decisions recorded for '{tool_name}')")
                return
            print(f"\nLast 10 calls to '{tool_name}':")
            print(f"  {'time':<17} {'step':<5} {'lat':<6} {'ok':<3} {'error':<14} args")
            for r in rows:
                ok = "✓" if r[3] else "✗"
                print(f"  {r[5][:16]:<17} {r[0]:<5} {r[2]:<6} {ok:<3} {r[4][:13]:<14} {r[1][:60]}")
            return

        # Default: tool_stats overview
        stats = self.decision_log.get_stats(min_uses=1)
        total = self.decision_log.get_total()
        print(f"\n[Decision Log] total rows: {total}")
        if not stats:
            print("  (no tool decisions recorded yet)")
            print("\n  Tip: run a tool task, decisions are auto-logged.")
            return
        print(f"\n  {'tool':<22} {'uses':<6} {'ok':<5} {'fail':<5} {'rate':<7} {'avg_ms':<8}")
        for s in stats:
            rate = f"{s['success_rate_pct']:.0f}%" if s['success_rate_pct'] is not None else "?"
            print(f"  {s['tool_name']:<22} {s['total_uses']:<6} "
                  f"{s['successes']:<5} {s['failures']:<5} {rate:<7} {s['avg_latency_ms'] or 0:<8.1f}")
            failures = self.decision_log.get_top_failure_modes(s['tool_name'])
            if failures:
                print(f"    ↳ common errors: {', '.join(failures)}")
        ts = self.reflection_store.get_stats()
        print(f"\n  Task reflections: {ts['total']} total, {ts['failures']} non-success")

    def _cmd_embedder(self, args: str) -> None:
        """Show embedder configuration + probe availability."""
        from src.memory.embedder import probe as embedder_probe
        from src.utils.config import get_config
        cfg = get_config()
        emb_cfg = cfg.get("memory.embedder") or {}
        print("\n[Embedder Config]")
        if emb_cfg:
            for k, v in emb_cfg.items():
                print(f"  {k}: {v}")
        else:
            print("  (not set in settings.yaml, falling back to env vars / defaults)")
        # Also read env vars
        for var in ("EMBED_PROVIDER", "EMBED_BASE_URL", "EMBED_MODEL"):
            v = os.environ.get(var)
            if v:
                print(f"  env {var}: {v}")

        print("\n[Availability Probe]")
        info = embedder_probe()
        if info["ok"]:
            print(f"  OK: {info['provider']} @ {info['base_url']} "
                  f"(model={info['model']}, dim={info.get('dim')})")
        else:
            print(f"  FAIL: {info.get('provider', '?')} @ {info.get('base_url', '?')}")
            print(f"    error: {info.get('error', 'unknown')}")


def main():
    from src.utils.migrate import run_migration
    run_migration(Path(__file__).resolve().parent)
    fsar = FSAR()
    fsar.start()


if __name__ == "__main__":
    main()

# SPDX-License-Identifier: MIT
"""Slash command executor for GUI chat — same backend stores as the CLI commands."""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING

from src.utils.logger import logger

if TYPE_CHECKING:
    from src.server.chat_engine import ChatEngine

HELP_TEXT = """**Available commands**

| Command | Description |
|---|---|
| `/help` | Show this help |
| `/memory [stats\\|sessions [N]\\|session <id>\\|delete <id>\\|search <kw>\\|clear]` | Memory database |
| `/history` | Recent messages in current session |
| `/search <keyword>` | Search long-term memory |
| `/clear` | Clear current conversation context |
| `/config` | Show active LLM provider config |
| `/tools` | List available tools |
| `/mcp [reload]` | MCP server status / reload |
| `/perm [mode <m>\\|trust <t>\\|deny <t>\\|grant <t>\\|revoke <t>\\|reset]` | Permissions |
| `/audit [N]` | Recent audit log |
| `/rate <1-5> [reason]` | Rate the most recent reply |
| `/profile [set <k> <v>\\|del <k>]` | User profile |
| `/prefs [set <k> <v>\\|get <k>\\|del <k>]` | Preferences |
| `/feedback` | Rating statistics |
| `/reflect` | Force immediate reflection |
| `/stats [recent\\|tool <name>]` | Tool decision-log aggregates |
| `/resume [id]` | Load a past session into context |
| `/exp [view <name>\|del <name>\|stale\|archive]` | Experiences CRUD |
| `/use <name> [task...]` | Load a learned skill/experience into context (optionally act on a task) |
| `/learn <name> <cat> "<desc>"` + body on next lines | Persist an experience |
| `/import <skill-folder-or-markdown>` | Import an external skill |
| `/remember "<fact>"` | Persist a cross-session fact |
| `/facts [keyword]` | List / search saved facts |
| `/skills [status\\|activity <name> enable\\|disable\\|delete <name>]` | External skills |
"""


async def execute(engine: "ChatEngine", line: str) -> str:
    first, _, rest = line.partition("\n")
    parts = first.split(maxsplit=1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""
    try:
        handler = _HANDLERS.get(cmd)
        if handler is None:
            return f"Unknown command: `{cmd}` — try `/help`."
        import inspect
        result = handler(engine, args, rest)
        if inspect.isawaitable(result):
            result = await result
        return result or "(done)"
    except Exception as e:
        logger.error(f"command {cmd} failed: {e}")
        return f"Command failed: {e}"


def _help(engine, args, body) -> str:
    return HELP_TEXT


def _memory(engine, args, body) -> str:
    parts = args.split()
    sub = parts[0].lower() if parts else ""
    rest = parts[1:]
    lm = engine.long_memory
    if sub in ("", "stats"):
        stats = engine.recall.stats()
        fb = stats["feedback"]
        return (
            "**Memory System Overview**\n\n"
            f"- Sessions: {stats['long_term']['total_sessions']}\n"
            f"- Messages: {stats['long_term']['total_messages']}\n"
            f"- Semantic: {stats['semantic_count']} (available: {stats['semantic_available']})\n"
            f"- Preferences: {stats['preferences_count']} · Patterns: {stats['patterns_count']}"
            f" · Profile: {stats['profile_count']}\n"
            f"- Ratings: {fb['total']} (avg={fb['avg']}, high≥4: {fb['high_count']}, low≤2: {fb['low_count']})\n"
            f"- Current session: `{engine.session_id}` ({engine.short_memory.length} context messages)"
        )
    if sub == "sessions":
        n = int(rest[0]) if rest and rest[0].isdigit() else 10
        rows = lm.list_sessions_with_count(limit=n)
        if not rows:
            return "(no sessions yet)"
        lines = ["**Recent sessions**", ""]
        for r in rows:
            lines.append(f"- `{r['session_id']}` — {r['count']} msgs, {str(r.get('last_ts', ''))[:16]}")
        return "\n".join(lines)
    if sub == "session" and rest:
        msgs = lm.get_session_messages(rest[0])
        if not msgs:
            return f"(no messages for session `{rest[0]}`)"
        lines = [f"**Session `{rest[0]}`** — {len(msgs)} messages", ""]
        for m in msgs[-50:]:
            lines.append(f"- **{m.role}**: {m.content[:200]}")
        return "\n".join(lines)
    if sub == "delete" and rest:
        n = lm.delete_session(rest[0])
        return f"Deleted session `{rest[0]}` ({n} rows)."
    if sub == "search" and rest:
        return _search(engine, " ".join(rest), "")
    if sub == "clear":
        n_msg = lm.clear_all()
        engine.semantic.clear()
        n_profile = engine.user_model.clear_all()
        engine.short_memory.clear()
        return (
            f"Cleared all memory: {n_msg} long-term message(s), semantic vectors, "
            f"{n_profile} user-model entries, and the current context."
        )
    return "Usage: `/memory [stats|sessions [N]|session <id>|delete <id>|search <kw>|clear]`"


def _history(engine, args, body) -> str:
    msgs = engine.short_memory.get_messages(last_n=20)
    if not msgs:
        return "(empty context)"
    return "\n".join(f"- **{m.role}**: {m.content[:200]}" for m in msgs)


def _search(engine, args, body) -> str:
    kw = args.strip()
    if not kw:
        return "Usage: `/search <keyword>`"
    hits = engine.long_memory.search(kw, limit=10)
    if not hits:
        return f"No matches for `{kw}`."
    lines = [f"**Matches for `{kw}`** ({len(hits)})", ""]
    for h in hits:
        lines.append(f"- [`{h.session_id}`] **{h.role}**: {h.content[:160]}")
    return "\n".join(lines)


def _clear(engine, args, body) -> str:
    engine.short_memory.clear()
    return "Context cleared."


def _config(engine, args, body) -> str:
    active = engine.config.get("llm.active", "")
    p = dict(engine.config.get_active_provider())
    if p.get("api_key"):
        p["api_key"] = p["api_key"][:6] + "…"
    return (
        f"**Active provider**: `{active or '(none)'}`\n\n"
        + "```json\n" + json.dumps(p, ensure_ascii=False, indent=2) + "\n```"
    )


def _tools(engine, args, body) -> str:
    tools = engine.registry.list_tools()
    lines = [f"**Tools** ({len(tools)})", ""]
    for t in tools:
        lines.append(f"- `{t.name}` [{t.risk_level}] — {t.description[:100]}")
    return "\n".join(lines)


async def _mcp(engine, args, body) -> str:
    sub = args.split()[0].lower() if args.split() else ""
    if sub == "reload":
        await engine.mcp.reload()
    names = engine.mcp.servers
    servers = engine.config.get("mcp.servers") or []
    lines = [f"**MCP servers** ({len(servers)} configured, {len(names)} running)", ""]
    for s in servers:
        name = s.get("name", "")
        state = "running" if name in names else ("enabled" if s.get("enabled") else "disabled")
        lines.append(f"- `{name}` [{state}] risk={s.get('risk_level', '?')}")
    return "\n".join(lines) if servers else "(no MCP servers configured)"


def _perm(engine, args, body) -> str:
    from src.security import load_permissions, save_permissions
    parts = args.split()
    sub = parts[0].lower() if parts else ""
    p = engine.permissions
    if sub == "":
        lines = [
            f"**Permission mode**: `{p.mode}`",
            f"- session trust: {sorted(p.session_trust) or '(none)'}",
            f"- session deny: {sorted(p.session_deny) or '(none)'}",
            "",
            "**Tool policies**",
        ]
        for name, cfg in p.tools.items():
            lines.append(f"- `{name}`: {json.dumps(cfg, ensure_ascii=False)[:120]}")
        return "\n".join(lines)
    if sub == "mode" and len(parts) >= 2 and parts[1] in ("strict", "normal", "trust"):
        p.mode = parts[1]
        return f"Mode set to `{parts[1]}` (session-scoped)."
    if sub == "trust" and len(parts) >= 2:
        p.set_session_trust(parts[1])
        return f"Session trust: `{parts[1]}`"
    if sub == "deny" and len(parts) >= 2:
        p.session_deny.add(parts[1])
        return f"Session deny: `{parts[1]}`"
    if sub == "grant" and len(parts) >= 2:
        p.set_session_trust(parts[1])
        save_permissions(p)
        return f"Permanently granted: `{parts[1]}`"
    if sub == "revoke" and len(parts) >= 2:
        p.set_permanent_deny(parts[1])
        save_permissions(p)
        return f"Permanently denied: `{parts[1]}`"
    if sub == "reset":
        engine.permissions = load_permissions()
        from src.security import RiskEngine
        engine.risk_engine = RiskEngine(engine.permissions)
        return "Permissions reloaded from yaml."
    return "Usage: `/perm [mode <strict|normal|trust>|trust <t>|deny <t>|grant <t>|revoke <t>|reset]`"


def _audit(engine, args, body) -> str:
    from src.security import tail as audit_tail
    parts = args.split()
    n = int(parts[0]) if parts and parts[0].isdigit() else 10
    entries = audit_tail(n)
    if not entries:
        return "(audit log is empty)"
    lines = [f"**Most recent {len(entries)} audit entries**", ""]
    for e in entries:
        err = f" err={e.get('error')}" if e.get("error") else ""
        lines.append(
            f"- [{e['ts'][:16]}] `{e['tool']}` verdict={e['verdict']}"
            f" user={e.get('user_response', '')} outcome={e.get('outcome', '?')}{err}"
        )
    return "\n".join(lines)


def _rate(engine, args, body) -> str:
    parts = args.split(maxsplit=1)
    if not parts:
        return "Usage: `/rate <1-5> [reason]`"
    try:
        rating = int(parts[0])
    except ValueError:
        return f"Rating must be an integer 1-5, got: {parts[0]!r}"
    if not (1 <= rating <= 5):
        return "Rating must be 1-5."
    reason = parts[1] if len(parts) > 1 else ""
    last = None
    for v in engine._msg_ids.values():
        last = v
    if last is None:
        return "No reply to rate yet."
    engine.feedback.add_or_update_rating(
        message_id=last, session_id=engine.session_id, rating=rating, reason=reason,
    )
    return f"Rated msg#{last} {rating}/5" + (f" — {reason}" if reason else "")


def _profile(engine, args, body) -> str:
    parts = args.split(maxsplit=2)
    um = engine.user_model
    if not parts:
        profile = um.get_profile()
        prefs = um.get_all_preferences()
        patterns = um.get_top_patterns(limit=10)
        lines = ["**User Profile**"]
        lines += [f"- {k}: {v}" for k, v in profile.items()] or ["- (empty)"]
        lines.append(f"\n**Preferences** ({len(prefs)})")
        lines += [f"- {k} = {p.value}" for k, p in prefs.items()]
        lines.append(f"\n**Patterns** ({len(patterns)})")
        lines += [f"- {p['pattern']} (×{p['count']})" for p in patterns]
        return "\n".join(lines)
    if parts[0] == "set" and len(parts) >= 3:
        um.set_profile(parts[1], parts[2], source="manual")
        return f"Profile updated: {parts[1]} = {parts[2]}"
    if parts[0] == "del" and len(parts) >= 2:
        return ("Deleted." if um.delete_profile(parts[1])
                else f"Not found: {parts[1]}")
    return "Usage: `/profile [set <k> <v>|del <k>]`"


def _prefs(engine, args, body) -> str:
    parts = args.split()
    um = engine.user_model
    if not parts:
        prefs = um.get_all_preferences()
        return "\n".join(
            [f"**Preferences** ({len(prefs)})"]
            + [f"- {k} = {p.value}" for k, p in prefs.items()]
        )
    if parts[0] == "set" and len(parts) >= 3:
        um.set_preference(parts[1], parts[2], source="explicit")
        return f"Preference set: {parts[1]} = {parts[2]}"
    if parts[0] == "get" and len(parts) >= 2:
        v = um.get_preference(parts[1])
        return f"{parts[1]} = {v!r}" if v is not None else f"{parts[1]} does not exist"
    if parts[0] == "del" and len(parts) >= 2:
        um.set_preference(parts[1], "", source="deleted")
        return f"Preference deleted: {parts[1]}"
    return "Usage: `/prefs [set <k> <v>|get <k>|del <k>]`"


def _feedback(engine, args, body) -> str:
    stats = engine.feedback.get_stats()
    lines = [
        "**Rating Statistics**",
        f"- Total: {stats['total']} · Average: {stats['avg']}",
        f"- High (≥4): {stats['high_count']} · Low (≤2): {stats['low_count']}",
    ]
    low = engine.feedback.get_low_rated(limit=5)
    if low:
        lines.append("\n**Low-rated samples**")
        for s in low:
            lines.append(f"- {s['rating']}/5 {s.get('reason', '')}: {s['content'][:80]}")
    return "\n".join(lines)


def _reflect(engine, args, body) -> str:
    from src.memory import IdleReflector
    client, model, _ = engine.client_and_model()
    reflector = IdleReflector(
        long_term=engine.long_memory,
        user_model=engine.user_model,
        feedback=engine.feedback,
        model=model,
    )
    if client is not None:
        try:
            reflector.set_llm(client)
        except Exception as e:
            logger.warning(f"reflect set_llm failed: {e}")
    report = reflector.reflect(force=True)
    if report is None:
        return "Reflection produced no report (not enough data?)."
    lines = ["**Reflection complete**"]
    if report.profile:
        lines += [f"- profile {k}: {v}" for k, v in report.profile.items()]
    if report.preferences:
        lines += [f"- pref {k} = {v}" for k, v in report.preferences.items()]
    if report.patterns:
        lines += [f"- pattern: {p['pattern']}" for p in report.patterns]
    return "\n".join(lines)


def _stats(engine, args, body) -> str:
    parts = args.split()
    sub = parts[0].lower() if parts else ""
    dl = engine.decision_log
    if sub == "recent":
        limit = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 10
        recent = engine.reflection_store.list_recent(limit=limit)
        if not recent:
            return "(no task reflections yet)"
        lines = [f"**Most recent {len(recent)} task reflections**", ""]
        for r in recent:
            lines.append(
                f"- [{r['created_at'][:16]}] `{r['task_id'][:20]}` outcome={r['outcome']}"
                f" steps={r['step_count']}"
                + (f" — {r['suggested_strategy'][:100]}" if r.get("suggested_strategy") else "")
            )
        return "\n".join(lines)
    if sub == "tool" and len(parts) >= 2:
        with dl._connect() as conn:
            rows = conn.execute(
                "SELECT step_no, args_summary, latency_ms, success, error_class, created_at"
                " FROM decision_log WHERE chosen_tool = ? ORDER BY created_at DESC LIMIT 10",
                (parts[1],),
            ).fetchall()
        if not rows:
            return f"(no decisions recorded for `{parts[1]}`)"
        lines = [f"**Last {len(rows)} calls to `{parts[1]}`**", ""]
        for r in rows:
            ok = "ok" if r[3] else f"fail({r[4]})"
            lines.append(f"- [{r[5][:16]}] {r[2]}ms {ok} — {r[1][:80]}")
        return "\n".join(lines)
    stats = dl.get_stats(min_uses=1)
    total = dl.get_total()
    lines = [f"**Decision Log** — {total} rows", ""]
    if not stats:
        return lines[0] + "\n\n(no tool decisions recorded yet)"
    lines.append("| tool | uses | ok | fail | rate | avg ms |")
    lines.append("|---|---|---|---|---|---|")
    for s in stats:
        rate = f"{s['success_rate_pct']:.0f}%" if s["success_rate_pct"] is not None else "?"
        lines.append(
            f"| `{s['tool_name']}` | {s['total_uses']} | {s['successes']}"
            f" | {s['failures']} | {rate} | {s['avg_latency_ms'] or 0:.0f} |"
        )
    ts = engine.reflection_store.get_stats()
    lines.append(f"\nTask reflections: {ts['total']} total, {ts['failures']} non-success")
    return "\n".join(lines)


def _resume(engine, args, body) -> str:
    sid = args.strip()
    lm = engine.long_memory
    if not sid:
        rows = lm.list_sessions_with_count(limit=20)
        if not rows:
            return "(no sessions to resume)"
        lines = ["**Sessions** — use `/resume <id>`", ""]
        for r in rows:
            lines.append(f"- `{r['session_id']}` — {r['count']} msgs")
        return "\n".join(lines)
    matches = [r["session_id"] for r in lm.list_sessions_with_count(limit=100)
               if r["session_id"].startswith(sid)]
    if not matches:
        return f"No session matches `{sid}`."
    msgs = lm.get_session_messages(matches[0])
    engine.short_memory.clear()
    for m in msgs[-50:]:
        engine.short_memory.add(m.role, m.content)
    return f"Resumed session `{matches[0]}` — loaded {min(len(msgs), 50)} messages into context."


def _exp(engine, args, body) -> str:
    from src.memory import ExperienceStore
    store = ExperienceStore()
    parts = args.split()
    if not parts:
        exps = store.list_for_index()
        if not exps:
            return "(no experiences yet — use `/learn` to add one)"
        lines = [f"**Active Experiences** ({len(exps)})", ""]
        for e in exps:
            lines.append(f"- [{e.category}] `{e.name}`: {e.description[:60]} (uses={e.use_count})")
        return "\n".join(lines)
    sub = parts[0].lower()
    if sub == "view" and len(parts) >= 2:
        exp = store.get_by_name(parts[1])
        if not exp:
            return f"Not found: {parts[1]}"
        store.bump_use(parts[1])
        return store.render_experience_body(exp)
    if sub == "del" and len(parts) >= 2:
        return (f"Deleted `{parts[1]}`" if store.delete_experience(parts[1])
                else f"Not found: {parts[1]}")
    if sub == "stale":
        return f"Marked {store.mark_stale(days=0)} experiences stale."
    if sub == "archive":
        return f"Archived {store.mark_archived(days=0)} experiences."
    return "Usage: `/exp [view <name>|del <name>|stale|archive]`"


def _learn(engine, args, body) -> str:
    from src.memory import Experience, ExperienceStore
    parts = args.split()
    if len(parts) < 3:
        return ('Usage: `/learn <name> <category> "<description>"` with the procedure '
                "body on the following lines of the same message.")
    name, category = parts[0], parts[1]
    description = " ".join(parts[2:]).strip().strip('"')[:60]
    body = (body or "").strip()
    if not body:
        return "Missing body — put the procedure text on the lines after the command."
    store = ExperienceStore()
    existing = store.get_by_name(name)
    now = datetime.now().isoformat(timespec="seconds")
    eid = store.upsert_experience(Experience(
        name=name, category=category, description=description, body=body,
        created_by="user", created_at=existing.created_at if existing else now,
        updated_at=now,
    ))
    op = "updated" if existing else "created"
    return f"Experience {op}: id={eid} `{name}` [{category}] — {description}"


def _import(engine, args, body) -> str:
    from pathlib import Path
    from src.tools.builtin.experience_import import import_markdown_file
    path = args.strip().strip('"')
    if not path:
        return "Usage: `/import <skill-folder-or-markdown>`"
    target = Path(path)
    if target.is_dir():
        from src.server.handlers.skill_install import install_skill_folder

        result = install_skill_folder(
            target,
            engine.config.get("memory.sqlite_path", "data/memory.db"),
        )
        lines = [f"**{result['action']}** `{result['name']}`"]
        lines.append(f"- id: {result['id']}")
        lines.append(f"- templates: {result['templates']}")
        lines.append(f"- scripts: {result['scripts']}")
        lines.append(f"- references: {result['references']}")
        lines += [f"- warning: {warning}" for warning in result["warnings"]]
        return "\n".join(lines)
    res = import_markdown_file(Path(path))
    if res is None:
        return "Import produced nothing."
    name, action, fields = res
    lines = [f"**{action}** `{name}`"]
    lines += [f"- {k}: {str(v)[:80]}" for k, v in fields.items() if v]
    return "\n".join(lines)


def _remember(engine, args, body) -> str:
    from src.memory import ExperienceStore
    text = (args + ("\n" + body if body else "")).strip().strip('"')
    if not text:
        return 'Usage: `/remember "<the fact to remember>"`'
    store = ExperienceStore()
    title = text.splitlines()[0]
    for sep in ("。", ".", "!", "?", "！", "？"):
        idx = title.find(sep)
        if idx > 0:
            title = title[:idx]
            break
    title = title.strip()[:60] or "fact"
    cid = store.add_chunk(source="user_fact", title=title, body=text)
    return f"Saved fact #{cid}: {title}"


def _facts(engine, args, body) -> str:
    from src.memory import ExperienceStore
    store = ExperienceStore()
    keyword = args.strip()
    if keyword:
        hits = store.search_chunks(keyword, limit=10)
        if not hits:
            return f"No facts match `{keyword}`."
        return "\n".join(
            [f"**Facts matching `{keyword}`**", ""]
            + [f"- [#{c.id}] **{c.title}**: {c.body[:100]}" for c in hits]
        )
    chunks = store.list_chunks(source="user_fact", limit=50)
    if not chunks:
        return '(no saved facts yet — try `/remember "something"`)'
    return "\n".join(
        [f"**Saved facts** ({len(chunks)})", ""]
        + [f"- [#{c.id}] **{c.title}**: {c.body[:100]}" for c in chunks]
    )


def _skills(engine, args, body) -> str:
    from src.memory import STATE_ACTIVE, STATE_ARCHIVED, ExperienceStore
    store = ExperienceStore()
    parts = args.split()
    sub = parts[0].lower() if parts else "status"
    if sub == "status":
        exps = store.list_for_index(
            categories=["external-skill"],
            include_states=["active", "stale", "archived"],
        )
        if not exps:
            return "(no external skills installed — install one or run `/learn`)"
        lines = [f"**External Skills** ({len(exps)})", ""]
        for e in exps:
            tag = "enabled" if e.state == "active" else e.state
            lines.append(f"- [{tag}] `{e.name}`: {e.description[:60]} (uses={e.use_count})")
        return "\n".join(lines)
    if sub == "activity" and len(parts) >= 3:
        name, action = parts[1], parts[2].lower()
        if action in ("enable", "on", "active"):
            return (f"Enabled `{name}`" if store.set_state(name, STATE_ACTIVE)
                    else f"Not found: {name}")
        if action in ("disable", "off", "archived"):
            return (f"Disabled `{name}`" if store.set_state(name, STATE_ARCHIVED)
                    else f"Not found: {name}")
        return f"Unknown action: {action!r}"
    if sub == "delete" and len(parts) >= 2:
        return (f"Deleted `{parts[1]}`" if store.delete_experience(parts[1])
                else f"Not found: {parts[1]}")
    return "Usage: `/skills [status|activity <name> enable|disable|delete <name>]`"


def _use(engine, args, body) -> str:
    from src.memory import ExperienceStore

    parts = args.split(maxsplit=1)
    name = parts[0].strip()
    if not name:
        return "Usage: `/use <experience-name> [task...]`"
    store = ExperienceStore()
    exp = store.get_by_name(name)
    if exp is None:
        return f"Not found: `{name}` — list available ones with `/exp`."
    rendered = store.render_experience_body(exp)
    if exp.category == "external-skill":
        # Attach the full SKILL.md + linked-file list + conflict rule, same as
        # experience_view — /use must not hand the agent a lossy summary.
        from src.tools.builtin.experience_tools import ExperienceViewTool
        rendered = ExperienceViewTool._append_skill_source(rendered, name)
    store.bump_use(name)
    conv_id = engine.active_conversation_id()
    if conv_id:
        engine._ensure_short(conv_id)  # noqa: SLF001 — engine ownership
        engine._short_cache[conv_id].append(  # noqa: SLF001
            {"role": "system", "content": f"Relevant learned skill/experience:\n\n{rendered}"}
        )
    task = parts[1].strip() if len(parts) > 1 else ""
    if task and conv_id:
        engine._command_followup = {"conversation_id": conv_id, "task": task}  # noqa: SLF001
        return f"Loaded experience `{name}` into context. Now handling: {task}"
    return f"Loaded experience `{name}` into this conversation's context."


_HANDLERS = {
    "/help": _help,
    "/memory": _memory,
    "/history": _history,
    "/search": _search,
    "/clear": _clear,
    "/config": _config,
    "/tools": _tools,
    "/mcp": _mcp,
    "/perm": _perm,
    "/audit": _audit,
    "/rate": _rate,
    "/profile": _profile,
    "/prefs": _prefs,
    "/feedback": _feedback,
    "/reflect": _reflect,
    "/stats": _stats,
    "/resume": _resume,
    "/exp": _exp,
    "/experiences": _exp,
    "/use": _use,
    "/learn": _learn,
    "/import": _import,
    "/remember": _remember,
    "/facts": _facts,
    "/memory_chunks": _facts,
    "/skills": _skills,
}

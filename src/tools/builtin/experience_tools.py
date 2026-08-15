"""FSAR Experience Layer tools — Phase 6.

Four tools, all SAFE risk:
- experience_view(name)            → load full body + bump use_count
- learn_experience(...)            → LLM/CLI can persist a new skill row
- list_experiences(category=None) → enumerate active rows for cold-start
- remember_fact(text, title?)      → persist a cross-session fact as memory_chunk
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from src.memory.experience_store import (
    ExperienceStore, Experience, ExperienceTemplate, ExperienceScript,
    ExperienceReference, STATE_ACTIVE,
)
from src.tools.registry import Tool
from src.utils.logger import logger


def _store() -> ExperienceStore:
    return ExperienceStore()


def _list_linked_files(skill_root: Path) -> list[str]:
    """List a skill's support files (reference docs, seed templates, helper
    scripts, validators) as absolute paths so the agent can read them on
    demand. Asset images are excluded — only the files that matter for
    following the skill are surfaced."""
    rels: list[str] = []
    refs = skill_root / "references"
    if refs.is_dir():
        rels.extend(str(p) for p in sorted(refs.glob("*.md")))
    tpl = skill_root / "assets"
    if tpl.is_dir():
        rels.extend(str(p) for p in sorted(tpl.glob("template-*.html")))
    scripts = skill_root / "scripts"
    if scripts.is_dir():
        rels.extend(str(p) for p in sorted(scripts.iterdir()) if p.is_file())
    for p in sorted(skill_root.iterdir()):
        if p.is_file() and p.name.startswith("validate") and p.suffix in (".mjs", ".js", ".py", ".sh"):
            rels.append(str(p))
    return rels


class ExperienceViewTool(Tool):
    """On-demand loader — returns full body + templates/scripts/references.

    Calling this bumps use_count + last_used_at on the row, so the lifecycle
    state machine keeps accurate.
    """

    @property
    def name(self) -> str:
        return "experience_view"

    @property
    def description(self) -> str:
        return ("Load the full procedure for a previously learned experience. "
                "Use this AFTER the system prompt suggests an experience name that "
                "matches your task. Returns procedure, pitfalls, templates, scripts.")

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The experience name to load (from the system-prompt index).",
                },
            },
            "required": ["name"],
        }

    @property
    def risk_level(self) -> str:
        return "SAFE"

    async def execute(self, *, name: str, **kwargs) -> str:
        store = _store()
        exp = store.get_by_name(name)
        if exp is None:
            return f"[NOT_FOUND] Experience '{name}' does not exist. Try list_experiences()."
        store.bump_use(name)
        body = store.render_experience_body(exp)
        if exp.category == "external-skill":
            body = self._append_skill_source(body, name)
        try:
            from src.memory.embedder import get_embedder
            embedder = get_embedder()
            if embedder is not None:
                from src.memory.experience_embedding import (
                    ensure_embedded,
                )
                ensure_embedded(embedder, exp.id, body)
        except Exception as e:
            logger.debug(f"embedding on view skipped: {e}")
        logger.debug(f"experience_view: {name} use_count={exp.use_count + 1}")
        return body

    @staticmethod
    def _append_skill_source(body: str, name: str) -> str:
        """Attach the external skill's authoritative SKILL.md + conflict rule.

        The path is derived from the skills root + experience name (matching
        skill_tool's convention), never stored in the experience row — so a
        moved/renamed skill keeps working. Degrades to the summary alone when
        the skill directory is missing.
        """
        from src.skills.gate import validate_subject_name
        from src.utils.fsar_home import get_fsar_home

        skill_md = get_fsar_home() / "skills" / validate_subject_name(name) / "SKILL.md"
        if not skill_md.is_file():
            return body
        try:
            raw = skill_md.read_text(encoding="utf-8")
        except OSError:
            return body
        linked = _list_linked_files(skill_md.parent)
        linked_block = ""
        if linked:
            linked_block = (
                "\n\nSupport files in this skill (paths). Read them ON DEMAND — open a "
                "single file with file_ops only when you need it; do not load them all:\n"
                + "\n".join(f"- {p}" for p in linked)
            )
        return (
            f"{body}\n\n"
            "---\n"
            f"Below is the external skill's original SKILL.md ({skill_md}); treat it as "
            "authoritative and read it in full — the Non-Negotiables at the end are "
            "hard requirements:\n"
            f"{raw}"
            f"{linked_block}\n\n"
            "[Conflict rule] If the user request conflicts with this SKILL.md: default to "
            "following the SKILL.md and state the conflict in one line; only follow the "
            "user if they explicitly know the conflict and insist."
        )


class LearnExperienceTool(Tool):
    """Persist a new experience row (or update an existing one by name).

    Available to both user (via /learn CLI) and the LLM (during conversation).
    No LLM round-trip — the caller supplies the fields directly.
    """

    @property
    def name(self) -> str:
        return "learn_experience"

    @property
    def description(self) -> str:
        return ("Persist a procedural skill into the experience layer. "
                "Provide name, category, short description, full procedure body, "
                "and optional trigger patterns / pitfalls / prerequisites. "
                "Re-using an existing name will UPDATE the row (preserve use_count).")

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Unique experience identifier, kebab/snake_case.",
                },
                "category": {
                    "type": "string",
                    "description": "Category for grouping (e.g. 'coding', 'file-management', 'research').",
                },
                "description": {
                    "type": "string",
                    "description": "≤60-char summary shown in the system-prompt index.",
                },
                "body": {
                    "type": "string",
                    "description": "Full procedure / how-to text.",
                },
                "trigger_patterns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                    "description": "Phrases that should surface this experience.",
                },
                "pitfalls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                    "description": "Known gotchas to warn the LLM about.",
                },
                "prerequisites": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                    "description": "Setup steps / required tooling.",
                },
            },
            "required": ["name", "category", "description", "body"],
        }

    @property
    def risk_level(self) -> str:
        return "SAFE"

    async def execute(self, *,
                      name: str,
                      category: str,
                      description: str,
                      body: str,
                      trigger_patterns: list[str] | None = None,
                      pitfalls: list[str] | None = None,
                      prerequisites: list[str] | None = None,
                      **kwargs) -> str:
        from src.skills.memory_sanitize import Sanitizer
        from src.utils.config import get_config
        if not Sanitizer(kwargs.get("_security_config") or get_config()).check(body).allowed:
            return "[BLOCKED: memory sanitization flagged]"
        store = _store()
        existing = store.get_by_name(name)
        from datetime import datetime
        now = datetime.now().isoformat(timespec="seconds")
        if existing is not None:
            exp = Experience(
                id=existing.id,
                name=name,
                category=category,
                description=description,
                body=body,
                trigger_patterns=list(trigger_patterns or []),
                pitfalls=list(pitfalls or []),
                prerequisites=list(prerequisites or []),
                use_count=existing.use_count,
                last_used_at=existing.last_used_at,
                state=existing.state,
                pinned=existing.pinned,
                created_by=existing.created_by,
                created_at=existing.created_at,
                updated_at=now,
            )
            source = "updated"
        else:
            exp = Experience(
                name=name,
                category=category,
                description=description,
                body=body,
                trigger_patterns=list(trigger_patterns or []),
                pitfalls=list(pitfalls or []),
                prerequisites=list(prerequisites or []),
                created_by="llm",
                created_at=now,
                updated_at=now,
            )
            source = "created"
        eid = store.upsert_experience(exp)
        logger.info(f"learn_experience: {source} id={eid} name={name!r} category={category}")
        return f"[OK] Experience '{name}' {source} (id={eid}, category={category})"


class ListExperiencesTool(Tool):

    @property
    def name(self) -> str:
        return "list_experiences"

    @property
    def description(self) -> str:
        return ("List experiences in the index. Returns up to 50 rows; "
                "default is 'active' state only. Pass category= to scope.")

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "default": None,
                    "description": "Optional category filter (e.g. 'coding').",
                },
            },
            "required": [],
        }

    @property
    def risk_level(self) -> str:
        return "SAFE"

    async def execute(self, *, category: Optional[str] = None, **kwargs) -> str:
        store = _store()
        cats = [category] if category else None
        exps = store.list_for_index(categories=cats)
        if not exps:
            msg = "(no experiences found)"
            if category:
                msg = f"(no experiences in category {category!r})"
            return msg
        lines = [f"{len(exps)} experiences:"]
        by_cat: dict[str, list] = {}
        for e in exps:
            by_cat.setdefault(e.category, []).append(e)
        for cat in sorted(by_cat):
            lines.append(f"  [{cat}]")
            for e in by_cat[cat]:
                desc = e.description or ""
                if len(desc) > 70:
                    desc = desc[:69] + "…"
                lines.append(f"    - {e.name}: {desc} (uses={e.use_count})")
        return "\n".join(lines)


class RememberFactTool(Tool):
    """Persist a short cross-session fact (e.g. 'My cat is named Beibei').

    Stored in memory_chunks. Auto-loaded via MemoryRecall into the LLM context
    block whenever keywords match. Survives across sessions.
    """

    @property
    def name(self) -> str:
        return "remember_fact"

    @property
    def description(self) -> str:
        return ("Persist a short cross-session fact to long-term memory. "
                "Used for things the user wants FSAR to remember across sessions "
                "(e.g. 'My cat is named Beibei', 'I work on Postgres 14 projects'). "
                "Pass the fact as text. Optional title gives it a short label.")

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The fact to remember (full sentence).",
                },
                "title": {
                    "type": "string",
                    "default": "",
                    "description": "Short label (auto-derived from text if omitted).",
                },
            },
            "required": ["text"],
        }

    @property
    def risk_level(self) -> str:
        return "SAFE"

    async def execute(self, *, text: str, title: str = "", **kwargs) -> str:
        store = _store()
        if not text.strip():
            return "[ERROR] text is empty"
        from src.skills.memory_sanitize import Sanitizer
        from src.utils.config import get_config
        if not Sanitizer(kwargs.get("_security_config") or get_config()).check(text).allowed:
            return "[BLOCKED: memory sanitization flagged]"
        title = (title or "").strip() or _auto_title(text)
        cid = store.add_chunk(source="user_fact", title=title, body=text.strip())
        logger.info(f"remember_fact: id={cid} title={title!r}")
        return f"[OK] Saved fact #{cid}: {title}"


def _auto_title(text: str, *, max_len: int = 40) -> str:
    """Derive a short label from the first sentence."""
    first = text.strip().splitlines()[0] if text.strip() else ""
    for sep in ("。", ".", "!", "?", "！", "？", ";", "；"):
        idx = first.find(sep)
        if idx > 0:
            first = first[:idx]
            break
    first = first.strip()
    if len(first) > max_len:
        first = first[:max_len - 1] + "…"
    return first or "fact"

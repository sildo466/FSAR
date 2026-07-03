"""Phase 6.3.5 — external skill markdown → experience row importer.

Drop a markdown file (with optional YAML frontmatter) into a directory, run
`/import <path>` and the file becomes an active experience row. Mirrors
Hermes's SKILL.md shape closely enough that community skills can be reused
with light edits — but DB is canonical, the .md file is just the input.

Frontmatter (optional, all fields optional except `name` and `category`):
---
name: download-organizer        # REQUIRED
category: file-management       # REQUIRED
description: Auto-classify ...  # ≤60 chars, shown in LLM index
body: |                          # optional inline body — overrides markdown body
    Step 1 ...
trigger_patterns:                # list, alternates with comma-separated string
    - organize downloads
pitfalls:
    - never delete originals
prerequisites:
    - python 3.11+
---

Sub-sections in the markdown body are auto-extracted:
    `## Templates: <name>` (or `## Template: <name>`) followed by ``` fenced code
    `## Scripts: <lang> <name>` followed by ``` fenced code
    `## References: <title>` followed by paragraphs
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from src.memory.experience_store import (
    Experience, ExperienceReference, ExperienceScript, ExperienceTemplate,
    ExperienceStore,
)
from src.utils.logger import logger


FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


@dataclass
class ParsedSkill:
    name: str
    category: str
    description: str
    body: str
    trigger_patterns: list[str]
    pitfalls: list[str]
    prerequisites: list[str]
    templates: list[ExperienceTemplate]
    scripts: list[ExperienceScript]
    references: list[ExperienceReference]
    source_path: str

    def summary(self) -> dict:
        return {
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "trigger_patterns": len(self.trigger_patterns),
            "pitfalls": len(self.pitfalls),
            "prerequisites": len(self.prerequisites),
            "templates": [t.name for t in self.templates],
            "scripts": [s.name for s in self.scripts],
            "references": [r.title for r in self.references],
            "source_path": self.source_path,
        }


def parse_skill_markdown(text: str, *, source_path: str = "") -> ParsedSkill:
    raw_yaml: dict[str, Any] = {}
    body = text
    m = FRONTMATTER_RE.match(text)
    if m:
        try:
            import yaml
            raw_yaml = yaml.safe_load(m.group(1)) or {}
        except Exception:
            raw_yaml = {}
        body = m.group(2)

    name = (raw_yaml.get("name") or "").strip()
    category = (raw_yaml.get("category") or "").strip()
    if not name:
        name = Path(source_path).stem if source_path else ""
    if not category:
        if name:
            category = "imported"
        else:
            raise ValueError("skill markdown requires at least a name (frontmatter or filename)")
    description = (raw_yaml.get("description") or "").strip()
    if len(description) > 60:
        description = description[:59] + "…"

    inline_body = raw_yaml.get("body")
    if isinstance(inline_body, str) and inline_body.strip():
        body_text = inline_body.rstrip()
    else:
        body_text = body.rstrip()

    return ParsedSkill(
        name=name,
        category=category,
        description=description,
        body=body_text,
        trigger_patterns=_ensure_list(raw_yaml.get("trigger_patterns")),
        pitfalls=_ensure_list(raw_yaml.get("pitfalls")),
        prerequisites=_ensure_list(raw_yaml.get("prerequisites")),
        templates=_extract_templates(body),
        scripts=_extract_scripts(body),
        references=_extract_references(body),
        source_path=source_path,
    )


def import_markdown_file(path: Path) -> tuple[str, str, dict] | None:
    """Parse a skill markdown file and persist it as an experience row.

    Returns (name, "created"|"updated", summary_dict) on success, None if the
    file is empty / unreadable.
    """
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"not a file: {path}")
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        print(f"(empty file: {path})")
        return None

    parsed = parse_skill_markdown(text, source_path=str(path))
    if not parsed.name:
        raise ValueError(f"could not infer name from {path} (no frontmatter, no filename)")
    if not parsed.body:
        raise ValueError(f"empty procedure body in {path}")

    store = ExperienceStore()
    existing = store.get_by_name(parsed.name)
    now = datetime.now().isoformat(timespec="seconds")
    exp = Experience(
        id=existing.id if existing else None,
        name=parsed.name,
        category=parsed.category,
        description=parsed.description,
        body=parsed.body,
        trigger_patterns=parsed.trigger_patterns,
        pitfalls=parsed.pitfalls,
        prerequisites=parsed.prerequisites,
        use_count=existing.use_count if existing else 0,
        last_used_at=existing.last_used_at if existing else None,
        state=existing.state if existing else Experience.state,
        pinned=existing.pinned if existing else False,
        created_by="import",
        created_at=existing.created_at if existing else now,
        updated_at=now,
    )
    store.save_experience_full(
        exp,
        templates=parsed.templates,
        scripts=parsed.scripts,
        references=parsed.references,
    )
    logger.info(
        f"experience_import: {'updated' if existing else 'created'} "
        f"name={parsed.name!r} category={parsed.category!r} "
        f"templates={len(parsed.templates)} scripts={len(parsed.scripts)} "
        f"refs={len(parsed.references)}"
    )
    action = "updated" if existing else "created"
    summary = {
        "category": parsed.category,
        "description": parsed.description,
        "trigger_patterns": ", ".join(parsed.trigger_patterns[:3]) if parsed.trigger_patterns else "",
        "pitfalls": ", ".join(parsed.pitfalls[:3]) if parsed.pitfalls else "",
        "templates": ", ".join(t.name for t in parsed.templates),
        "scripts": ", ".join(s.name for s in parsed.scripts),
        "references": ", ".join(r.title for r in parsed.references),
        "source_path": parsed.source_path,
    }
    return parsed.name, action, summary


# ---------- internals ----------

def _ensure_list(v: Any) -> list[str]:
    if v is None or v == "":
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str):
        return [s.strip() for s in re.split(r"[,\n]", v) if s.strip()]
    return [str(v)]


_CODE_FENCE_RE = re.compile(r"```([a-zA-Z0-9_+-]*)\n(.*?)```", re.DOTALL)


def _extract_templates(text: str) -> list[ExperienceTemplate]:
    """Sections matching: `## Templates: name` (or `Template`) + fenced code."""
    out: list[ExperienceTemplate] = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^##\s*Templates?:\s*(.+?)\s*$", line, re.IGNORECASE)
        if not m:
            i += 1
            continue
        name = m.group(1).strip()
        i += 1
        block: list[str] = []
        fence_match: re.Match | None = None
        while i < len(lines):
            cur = lines[i]
            if cur.strip().startswith("```"):
                fence_match = re.match(r"```([a-zA-Z0-9_+-]*)", cur.strip())
                i += 1
                break
            i += 1
        if fence_match is None:
            continue
        while i < len(lines) and not lines[i].strip().startswith("```"):
            block.append(lines[i])
            i += 1
        if i < len(lines):
            i += 1
        out.append(ExperienceTemplate(name=name, content="\n".join(block).rstrip()))
    return out


def _extract_scripts(text: str) -> list[ExperienceScript]:
    """Sections matching: `## Scripts: [lang] name` + fenced code.

    If `lang` is omitted, defaults to 'python' (matches fenced ```python blocks).
    """
    out: list[ExperienceScript] = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^##\s*Scripts?:\s*(?:(\S+)\s+)?(.+?)\s*$", line, re.IGNORECASE)
        if not m:
            i += 1
            continue
        lang = (m.group(1) or "python").strip().lower()
        name = m.group(2).strip()
        i += 1
        block: list[str] = []
        fence_lang: str | None = None
        while i < len(lines):
            cur = lines[i]
            stripped = cur.strip()
            if stripped.startswith("```"):
                fence_lang = re.match(r"```([a-zA-Z0-9_+-]*)", stripped)
                i += 1
                break
            i += 1
        if fence_lang is None:
            continue
        actual_lang = (fence_lang.group(1) or lang).lower() or "python"
        while i < len(lines) and not lines[i].strip().startswith("```"):
            block.append(lines[i])
            i += 1
        if i < len(lines):
            i += 1
        out.append(ExperienceScript(name=name, language=actual_lang,
                                   content="\n".join(block).rstrip()))
    return out


def _extract_references(text: str) -> list[ExperienceReference]:
    """Sections matching: `## References: title` + body (until next ## or EOF)."""
    out: list[ExperienceReference] = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^##\s*References?:\s*(.+?)\s*$", line, re.IGNORECASE)
        if not m:
            i += 1
            continue
        title = m.group(1).strip()
        i += 1
        body_lines: list[str] = []
        while i < len(lines) and not lines[i].lstrip().startswith("## "):
            body_lines.append(lines[i])
            i += 1
        body = "\n".join(body_lines).strip()
        if not body:
            continue
        url_match = re.search(r"https?://\S+", body)
        out.append(ExperienceReference(
            title=title, body=body,
            source="paste",
            source_url=url_match.group() if url_match else "",
            created_at=datetime.now().isoformat(timespec="seconds"),
        ))
    return out


def import_directory(dir_path: Path) -> list[tuple[str, str]]:
    """Import every *.md under dir_path (recursive). Returns list of (name, action)."""
    out: list[tuple[str, str]] = []
    if not dir_path.exists():
        raise FileNotFoundError(f"not a directory: {dir_path}")
    for md in sorted(dir_path.rglob("*.md")):
        try:
            res = import_markdown_file(md)
        except Exception as e:
            logger.warning(f"import skipped {md}: {e}")
            continue
        if res is None:
            continue
        out.append((res[0], res[1]))
    return out

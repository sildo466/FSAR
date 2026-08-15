"""Mechanical skill-compliance gate.

Soft instructions (SKILL.md in context, "FOLLOW it" framing) don't move a
reluctant model — only a mechanical check plus forced rework does. These
helpers check a task's output against the active external skill and describe
the gap.

Template compliance: a task whose skill provides a seed template should end
up with an index.html that shares the template's structural markers; falling
under the threshold means the agent wrote from scratch instead of copying.
"""

from __future__ import annotations

import time
from pathlib import Path

from src.skills.gate import validate_subject_name
from src.utils.fsar_home import get_fsar_home

TEMPLATE_MARKERS = (
    "POSTERS_HERE", "data-theme", "data-accent",
    "pipeline-v", "marginalia", "ledger-row",
)
TEMPLATE_MIN_SHARED = 3


def resolve_skill_dir(skill_name: str) -> Path | None:
    d = get_fsar_home() / "skills" / validate_subject_name(skill_name)
    return d if d.is_dir() else None


def find_skill_template(skill_dir: Path) -> Path | None:
    tpl = skill_dir / "assets"
    if tpl.is_dir():
        for p in sorted(tpl.glob("template-*.html")):
            return p
    return None


def find_skill_validator(skill_dir: Path) -> Path | None:
    for p in sorted(skill_dir.iterdir()):
        if p.is_file() and p.name.startswith("validate") and p.suffix in (".mjs", ".js", ".py", ".sh"):
            return p
    return None


def find_task_index_html(output_root: Path, max_age: float = 1200.0) -> Path | None:
    """Newest index.html under a direct subdir of output_root, modified recently."""
    if not output_root.is_dir():
        return None
    now = time.time()
    best: Path | None = None
    best_age = float("inf")
    for child in output_root.iterdir():
        if not child.is_dir():
            continue
        idx = child / "index.html"
        if not idx.is_file():
            continue
        try:
            age = now - idx.stat().st_mtime
        except OSError:
            continue
        if age < best_age and age < max_age:
            best, best_age = idx, age
    return best


def template_compliance(task_html: Path, template: Path) -> list[str]:
    """Return a list of issues; empty means the task follows the template."""
    try:
        html = task_html.read_text(encoding="utf-8", errors="replace")
        tpl = template.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ["无法读取任务 index.html 或 seed 模板。"]
    shared = [m for m in TEMPLATE_MARKERS if m in tpl and m in html]
    if len(shared) < TEMPLATE_MIN_SHARED:
        return [
            f"任务 index.html 未使用 seed 模板：与 {template.name} 仅共享 "
            f"{len(shared)}/{len(TEMPLATE_MARKERS)} 个结构标记 "
            f"({', '.join(TEMPLATE_MARKERS)})，说明是手写 CSS 而非复制模板。"
        ]
    return []

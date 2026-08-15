"""Auto-register external skills from the skills root into the experience store.

Skills live as directories under `<fsar_home>/skills/<name>/SKILL.md` — the
same directory convention the `npx skills` ecosystem and manual installs use.
This scans that root and upserts each discovered SKILL.md as an
external-skill experience, so dropping a skill into the skills root makes it
immediately available in the LLM experience index (and loadable via
`experience_view`, which attaches the full SKILL.md on demand).
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.memory.experience_store import Experience, ExperienceStore

logger = logging.getLogger(__name__)


def sync_skills_from_disk(
    store: ExperienceStore | None = None,
    skills_root: Path | None = None,
) -> int:
    """Scan the skills root and register each SKILL.md as an experience.

    Returns the number of skills newly registered. Existing external-skill
    experiences are left untouched (their curated body stays); only a
    description drift on an existing row is refreshed.
    """
    from src.tools.builtin.experience_import import parse_skill_markdown
    from src.utils.fsar_home import get_fsar_home

    store = store or ExperienceStore()
    root = skills_root or (get_fsar_home() / "skills")
    if not root.is_dir():
        return 0

    added = 0
    for skill_dir in sorted(root.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            continue
        try:
            parsed = parse_skill_markdown(
                skill_md.read_text(encoding="utf-8"),
                source_path=str(skill_md),
            )
        except Exception as e:
            logger.debug(f"skill sync skipped {skill_md}: {e}")
            continue

        existing = store.get_by_name(parsed.name)
        if existing is not None:
            if (
                existing.category == "external-skill"
                and existing.description != parsed.description
            ):
                existing.description = parsed.description
                store.upsert_experience(existing)
            continue

        store.upsert_experience(Experience(
            name=parsed.name,
            category="external-skill",
            description=parsed.description,
            body=f"已安装的外部 Skill：{skill_md}\n"
                 "执行前调用 experience_view 加载完整 SKILL.md 并按它执行。",
        ))
        added += 1
    return added

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from src.memory.experience_store import Experience, ExperienceStore
from src.tools.builtin.experience_import import parse_skill_folder


def install_skill_folder(folder_path: str | Path, db_path: str | Path) -> dict[str, object]:
    parsed, warnings = parse_skill_folder(folder_path)
    store = ExperienceStore(db_path=db_path)
    existing = store.get_by_name(parsed.name)
    now = datetime.now().isoformat(timespec="seconds")
    experience = Experience(
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
    experience_id = store.save_experience_full(
        experience,
        templates=parsed.templates,
        scripts=parsed.scripts,
        references=parsed.references,
    )
    return {
        "id": experience_id,
        "name": parsed.name,
        "action": "updated" if existing else "created",
        "category": parsed.category,
        "templates": len(parsed.templates),
        "scripts": len(parsed.scripts),
        "references": len(parsed.references),
        "warnings": warnings,
    }

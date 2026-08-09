from __future__ import annotations

import stat
from dataclasses import dataclass
from pathlib import Path

import yaml

from src.memory.experience_store import (
    ExperienceReference,
    ExperienceScript,
    ExperienceTemplate,
)
from src.tools.builtin.experience_import import ParsedSkill, parse_skill_markdown


MAX_SIBLING_BYTES = 1024 * 1024

SCRIPT_LANGUAGES = {
    ".bat": "batch",
    ".cmd": "batch",
    ".js": "javascript",
    ".ps1": "powershell",
    ".py": "python",
    ".rb": "ruby",
    ".sh": "bash",
    ".ts": "typescript",
}


class SkillFolderError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class SkillFolderContents:
    parsed: ParsedSkill
    templates: tuple[ExperienceTemplate, ...]
    scripts: tuple[ExperienceScript, ...]
    references: tuple[ExperienceReference, ...]
    warnings: tuple[str, ...]


def parse_skill_folder_contents(folder_path: str | Path) -> SkillFolderContents:
    folder = Path(folder_path)
    _validate_folder(folder)
    skill_md = _find_skill_md(folder)

    try:
        text = skill_md.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise SkillFolderError("skill_md_unreadable") from exc

    _validate_frontmatter(text)
    parsed = parse_skill_markdown(text, source_path=str(skill_md))

    warnings: list[str] = []
    scripts = _read_scripts(_sibling_directory(folder, "scripts"), warnings)
    references = _read_references(_sibling_directory(folder, "references"), warnings)
    templates = _read_templates(_sibling_directory(folder, "templates"), warnings)
    return SkillFolderContents(
        parsed=parsed,
        templates=tuple(templates),
        scripts=tuple(scripts),
        references=tuple(references),
        warnings=tuple(warnings),
    )


def _validate_folder(folder: Path) -> None:
    try:
        mode = folder.stat().st_mode
    except FileNotFoundError as exc:
        raise SkillFolderError("folder_not_found") from exc
    except OSError as exc:
        raise SkillFolderError("folder_unreadable") from exc
    if not stat.S_ISDIR(mode):
        raise SkillFolderError("folder_not_directory")


def _find_skill_md(folder: Path) -> Path:
    try:
        entries = list(folder.iterdir())
    except OSError as exc:
        raise SkillFolderError("folder_unreadable") from exc

    matches: list[Path] = []
    for entry in entries:
        if entry.name.casefold() != "skill.md":
            continue
        try:
            is_file = stat.S_ISREG(entry.stat().st_mode)
        except OSError as exc:
            raise SkillFolderError("skill_md_unreadable") from exc
        if is_file:
            matches.append(entry)

    if not matches:
        raise SkillFolderError("skill_md_missing")
    if len(matches) != 1:
        raise SkillFolderError("skill_md_ambiguous")
    return matches[0]


def _validate_frontmatter(text: str) -> None:
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise SkillFolderError("invalid_frontmatter")
    try:
        end = lines.index("---", 1)
    except ValueError as exc:
        raise SkillFolderError("invalid_frontmatter") from exc

    try:
        frontmatter = yaml.safe_load("\n".join(lines[1:end]))
    except yaml.YAMLError as exc:
        raise SkillFolderError("invalid_frontmatter") from exc
    if not isinstance(frontmatter, dict):
        raise SkillFolderError("invalid_frontmatter")
    if not isinstance(frontmatter.get("name"), str) or not frontmatter["name"].strip():
        raise SkillFolderError("missing_name")
    if not isinstance(frontmatter.get("category"), str) or not frontmatter["category"].strip():
        raise SkillFolderError("missing_category")


def _sibling_directory(folder: Path, name: str) -> Path | None:
    try:
        return next((entry for entry in folder.iterdir() if entry.name == name), None)
    except OSError:
        return None


def _read_scripts(directory: Path | None, warnings: list[str]) -> list[ExperienceScript]:
    return [
        ExperienceScript(
            name=path.name,
            language=SCRIPT_LANGUAGES.get(path.suffix.lower(), "text"),
            content=content,
        )
        for path, content in _read_siblings(directory, "scripts", warnings)
    ]


def _read_references(directory: Path | None, warnings: list[str]) -> list[ExperienceReference]:
    return [
        ExperienceReference(title=path.name, body=content, source="file")
        for path, content in _read_siblings(directory, "references", warnings)
    ]


def _read_templates(directory: Path | None, warnings: list[str]) -> list[ExperienceTemplate]:
    return [
        ExperienceTemplate(name=path.name, content=content)
        for path, content in _read_siblings(directory, "templates", warnings)
    ]


def _read_siblings(
    directory: Path | None,
    kind: str,
    warnings: list[str],
) -> list[tuple[Path, str]]:
    if directory is None:
        return []
    try:
        mode = directory.stat().st_mode
    except FileNotFoundError:
        return []
    except OSError:
        warnings.append(f"stat_error: {kind}")
        return []
    if not stat.S_ISDIR(mode):
        return []

    try:
        entries = sorted(directory.iterdir(), key=lambda path: (path.name.casefold(), path.name))
    except OSError:
        warnings.append(f"read_dir: {kind}")
        return []

    result: list[tuple[Path, str]] = []
    for path in entries:
        relative = f"{kind}/{path.name}"
        try:
            file_stat = path.stat()
        except OSError:
            warnings.append(f"stat_error: {relative}")
            continue
        if not stat.S_ISREG(file_stat.st_mode):
            continue
        if file_stat.st_size > MAX_SIBLING_BYTES:
            warnings.append(f"size_cap: {relative}")
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            warnings.append(f"invalid_utf8: {relative}")
            continue
        except OSError:
            warnings.append(f"read_error: {relative}")
            continue
        result.append((path, content))
    return result

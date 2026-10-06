# SPDX-License-Identifier: MIT
"""The gate: what may leave a staging copy, and how it leaves.

The whole safety model rests on one property — promotion writes a commit onto
a dedicated branch and executes nothing. These tests are built to fail if that
stops being true.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.server.promote_gate import (
    EXECUTION_SURFACE, changed_entries, changed_paths, classify, promote,
)


def _c(*paths: str):
    """Classify plain-mode paths: the shape a tracked edit arrives in."""
    return classify([("100644", "100644", path) for path in paths])


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
    verdict = _c("src/app.py", "docs/readme.md")
    assert verdict.allowed is True
    assert verdict.reason == ""


def test_a_write_under_dot_git_rejects_the_whole_contribution() -> None:
    """Not just that file: the whole contribution. A commit that touches the
    repository's own metadata is not a contribution."""
    verdict = _c("src/app.py", ".git/hooks/pre-commit")
    assert verdict.allowed is False
    assert ".git" in verdict.reason


def test_a_bare_dot_git_path_is_refused_too() -> None:
    assert _c(".git").allowed is False


def test_the_execution_surface_is_refused() -> None:
    for path in EXECUTION_SURFACE:
        verdict = _c(path, "src/app.py")
        assert verdict.allowed is False, path
        assert path in verdict.reason


def test_a_workflow_file_is_refused() -> None:
    assert _c(".github/workflows/ci.yml").allowed is False


def test_a_backslash_path_cannot_sneak_past() -> None:
    assert _c("src\\app.py").allowed is True
    assert _c(".git\\hooks\\pre-commit").allowed is False


def test_an_absolute_or_escaping_path_is_refused() -> None:
    assert _c("../outside.py").allowed is False
    assert _c("/etc/passwd").allowed is False


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


def test_a_new_file_arrives_with_its_mode(tmp_path) -> None:
    project = _project(tmp_path)
    stage, baseline = _stage(tmp_path, project)
    (stage / "new.py").write_text("x = 1\n", encoding="utf-8")

    assert changed_entries(stage, baseline) == [("000000", "100644", "new.py")]


def test_an_edited_file_arrives_with_both_modes(tmp_path) -> None:
    project = _project(tmp_path)
    stage, baseline = _stage(tmp_path, project)
    (stage / "README.md").write_text("hello world\n", encoding="utf-8")

    assert changed_entries(stage, baseline) == [("100644", "100644", "README.md")]


def test_a_real_symlink_arrives_as_mode_120000(tmp_path) -> None:
    project = _project(tmp_path)
    stage, baseline = _stage(tmp_path, project)
    try:
        (stage / "link").symlink_to("README.md")
    except (OSError, NotImplementedError):
        pytest.skip("this platform cannot make a symlink without privileges")

    entries = changed_entries(stage, baseline)

    assert entries == [("000000", "120000", "link")]
    assert classify(entries).allowed is False


def test_a_symlink_is_refused() -> None:
    verdict = classify([("000000", "120000", "link")])
    assert verdict.allowed is False
    assert "symlink" in verdict.reason


def test_a_gitlink_is_refused() -> None:
    assert classify([("000000", "160000", "sub")]).allowed is False


def test_an_executable_is_refused() -> None:
    verdict = classify([("000000", "100755", "tool")])
    assert verdict.allowed is False
    assert "executable" in verdict.reason


def test_a_mode_change_is_refused() -> None:
    verdict = classify([("100755", "100644", "tool")])
    assert verdict.allowed is False
    assert "mode" in verdict.reason


def test_a_deletion_is_not_a_mode_change() -> None:
    assert classify([("100644", "000000", "gone.py")]).allowed is True


def test_a_new_plain_file_is_not_a_mode_change() -> None:
    assert classify([("000000", "100644", "new.py")]).allowed is True


@pytest.mark.parametrize("path", [
    ".gitmodules",
    ".envrc",
    "vite.config.js",
    "webpack.config.ts",
    "rollup.config.mjs",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "Jenkinsfile",
    ".gitlab-ci.yml",
    ".circleci/config.yml",
    ".travis.yml",
    ".devcontainer/devcontainer.json",
    ".npmrc",
    ".pypirc",
    ".netrc",
    "scripts/setup.sh",
    "tool.ps1",
    "run.bat",
    "run.cmd",
])
def test_a_real_name_on_the_execution_surface_is_refused(path: str) -> None:
    """Named files, not the patterns themselves: `_c("*.sh")` would pass
    against the pattern it is meant to stand for."""
    verdict = _c(path)
    assert verdict.allowed is False, path
    assert path in verdict.reason

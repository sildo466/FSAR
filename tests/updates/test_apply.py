# SPDX-License-Identifier: MIT
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.updates.apply import (
    UpdateRefused,
    apply_plan,
    build_plan,
    target_branch_for,
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=T", *args],
        cwd=str(repo), check=True, capture_output=True, text=True,
    )


def _commit(repo: Path, name: str, text: str) -> None:
    (repo / name).write_text(text)
    _git(repo, "add", name)
    _git(repo, "commit", "-q", "-m", f"add {name}")


def _branch_names(repo: Path) -> set[str]:
    """Local branch names, resolved from full refs.

    `%(refname:short)` answers `heads/v0.6.0` once a tag shadows the branch, so
    a `name in branches` check silently stops detecting a survivor.
    """
    out = subprocess.run(
        ["git", "for-each-ref", "--format=%(refname)", "refs/heads/"],
        cwd=str(repo), check=True, capture_output=True, text=True,
    ).stdout
    return {
        line.strip().removeprefix("refs/heads/")
        for line in out.splitlines()
        if line.strip()
    }


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repo with main at v0.5.0 and a beta branch at v0.6.0-beta1."""
    origin = tmp_path / "origin"
    origin.mkdir()
    _git(origin, "init", "-q", "-b", "main")
    _commit(origin, "a.txt", "a")
    _git(origin, "tag", "v0.5.0")

    _git(origin, "checkout", "-q", "-b", "v0.6.0")
    _commit(origin, "b.txt", "b")
    _git(origin, "tag", "v0.6.0-beta1")

    work = tmp_path / "work"
    subprocess.run(["git", "clone", "-q", str(origin), str(work)],
                   check=True, capture_output=True, text=True)
    # origin is left on v0.6.0, so clone has already created and checked out
    # that local branch -- `checkout -b v0.6.0` here would fail with
    # "a branch named 'v0.6.0' already exists".
    assert subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=str(work), check=True, capture_output=True, text=True,
    ).stdout.strip() == "v0.6.0"
    return work


def test_stable_target_maps_to_main():
    assert target_branch_for("v0.7.0") == "main"


def test_beta_target_maps_to_its_own_branch():
    assert target_branch_for("v0.6.0-beta1") == "v0.6.0"
    assert target_branch_for("v0.7.0-beta2") == "v0.7.0"


def test_plan_for_same_branch_is_a_plain_pull(repo: Path):
    plan = build_plan(repo, target_tag="v0.6.0-beta2", current_tag="v0.6.0-beta1")
    assert plan.current_branch == "v0.6.0"
    assert plan.target_branch == "v0.6.0"
    assert ("pull", "--ff-only") in plan.steps
    assert plan.drop_branch is None


def test_plan_never_contains_push(repo: Path):
    """The app ships to users without repo write access; remote writes are out."""
    for target, current in (("v0.7.0", "v0.6.0-beta1"), ("v0.6.0-beta2", "v0.5.0")):
        plan = build_plan(repo, target_tag=target, current_tag=current)
        flat = " ".join(" ".join(step) for step in plan.steps)
        assert "push" not in flat
        assert not (plan.drop_branch and "remote" in plan.drop_branch)


def test_plan_refuses_on_tracked_modifications(repo: Path):
    (repo / "a.txt").write_text("dirty")
    with pytest.raises(UpdateRefused) as excinfo:
        build_plan(repo, target_tag="v0.7.0", current_tag="v0.6.0-beta1")
    assert "uncommitted" in str(excinfo.value)


def test_plan_allows_untracked_files(repo: Path):
    (repo / "scratch.txt").write_text("untracked")
    plan = build_plan(repo, target_tag="v0.7.0", current_tag="v0.6.0-beta1")
    assert plan.target_branch == "main"


def test_plan_refuses_mid_merge(repo: Path):
    """Both sides must touch the same file, otherwise the merge fast-forwards
    and leaves no MERGE_HEAD behind."""
    _git(repo, "checkout", "-q", "-b", "other")
    (repo / "a.txt").write_text("other side")
    _git(repo, "commit", "-q", "-am", "other side")
    _git(repo, "checkout", "-q", "v0.6.0")
    (repo / "a.txt").write_text("beta side")
    _git(repo, "commit", "-q", "-am", "beta side")
    subprocess.run(["git", "merge", "other"], cwd=str(repo), capture_output=True)
    with pytest.raises(UpdateRefused) as excinfo:
        build_plan(repo, target_tag="v0.7.0", current_tag="v0.6.0-beta1")
    assert "merge" in str(excinfo.value)


def test_plan_refuses_detached_head(repo: Path):
    _git(repo, "checkout", "-q", "--detach", "v0.6.0-beta1")
    with pytest.raises(UpdateRefused) as excinfo:
        build_plan(repo, target_tag="v0.7.0", current_tag="v0.6.0-beta1")
    assert "detached" in str(excinfo.value)


def test_leaving_beta_for_stable_drops_the_beta_branch(repo: Path):
    plan = build_plan(repo, target_tag="v0.7.0", current_tag="v0.6.0-beta1")
    assert plan.target_branch == "main"
    assert plan.drop_branch == "v0.6.0"


def test_staying_on_stable_never_drops_main(repo: Path):
    _git(repo, "checkout", "-q", "main")
    plan = build_plan(repo, target_tag="v0.7.0", current_tag="v0.5.0")
    assert plan.drop_branch is None


def test_apply_keeps_an_unmerged_branch(repo: Path, tmp_path: Path):
    """v0.6.0 is not contained in main, so it must survive the update."""
    plan = build_plan(repo, target_tag="v0.7.0", current_tag="v0.6.0-beta1")
    result = apply_plan(repo, plan)
    assert result["branch"] == "main"
    assert result["dropped_branch"] is None
    assert result["kept_branch"] == "v0.6.0"
    assert "v0.6.0" in _branch_names(repo)


def test_apply_drops_a_fully_merged_branch(tmp_path: Path):
    origin = tmp_path / "origin"
    origin.mkdir()
    _git(origin, "init", "-q", "-b", "main")
    _commit(origin, "a.txt", "a")
    _git(origin, "tag", "v0.5.0")
    _git(origin, "checkout", "-q", "-b", "v0.6.0")
    _commit(origin, "b.txt", "b")
    # merge the beta work into main so the branch is fully contained
    _git(origin, "checkout", "-q", "main")
    _git(origin, "merge", "-q", "--no-ff", "-m", "merge v0.6.0", "v0.6.0")
    _git(origin, "tag", "v0.6.0")

    work = tmp_path / "work"
    subprocess.run(["git", "clone", "-q", str(origin), str(work)],
                   check=True, capture_output=True, text=True)
    _git(work, "checkout", "-q", "-b", "v0.6.0", "origin/v0.6.0")

    plan = build_plan(work, target_tag="v0.6.0", current_tag="v0.6.0-beta1")
    assert plan.drop_branch == "v0.6.0"
    result = apply_plan(work, plan)
    assert result["dropped_branch"] == "v0.6.0"
    assert result["kept_branch"] is None
    assert "v0.6.0" not in _branch_names(work)
    # the tag must survive: only local branches are ever deleted
    tags = subprocess.run(
        ["git", "tag", "--list", "v0.6.0"],
        cwd=str(work), check=True, capture_output=True, text=True,
    ).stdout.split()
    assert tags == ["v0.6.0"]


def test_gate_resolves_the_branch_not_a_shadowing_tag(tmp_path: Path):
    """A promoted release leaves tag v0.6.0 pointing at main while branch
    v0.6.0 may still hold unmerged work. Resolving the bare name finds the tag,
    reports "contained", and deletes work that was never merged."""
    origin = tmp_path / "origin"
    origin.mkdir()
    _git(origin, "init", "-q", "-b", "main")
    _commit(origin, "a.txt", "a")
    _git(origin, "tag", "v0.5.0")

    _git(origin, "checkout", "-q", "-b", "v0.6.0")
    _commit(origin, "unmerged.txt", "work that never reached main")
    _git(origin, "checkout", "-q", "main")
    _commit(origin, "a.txt", "b")
    _git(origin, "tag", "v0.6.0")  # tag on main, branch still unmerged

    work = tmp_path / "work"
    subprocess.run(["git", "clone", "-q", str(origin), str(work)],
                   check=True, capture_output=True, text=True)
    _git(work, "checkout", "-q", "-b", "v0.6.0", "origin/v0.6.0")

    plan = build_plan(work, target_tag="v0.7.0", current_tag="v0.6.0-beta1")
    assert plan.drop_branch == "v0.6.0"

    result = apply_plan(work, plan)
    assert result["dropped_branch"] is None
    assert result["kept_branch"] == "v0.6.0"
    assert "v0.6.0" in _branch_names(work)


def test_current_branch_ignores_a_shadowing_tag(tmp_path: Path):
    """rev-parse/symbolic-ref answer `heads/v0.6.0` here; that would corrupt
    every downstream comparison."""
    origin = tmp_path / "origin"
    origin.mkdir()
    _git(origin, "init", "-q", "-b", "main")
    _commit(origin, "a.txt", "a")
    _git(origin, "tag", "v0.6.0")
    _git(origin, "checkout", "-q", "-b", "v0.6.0")
    _commit(origin, "b.txt", "b")

    work = tmp_path / "work"
    subprocess.run(["git", "clone", "-q", str(origin), str(work)],
                   check=True, capture_output=True, text=True)
    # origin's HEAD is v0.6.0, so clone already checked that branch out. Asking
    # for it again would fail; the point is what `branch --show-current` answers
    # now that tag v0.6.0 shadows the name.
    plan = build_plan(work, target_tag="v0.7.0", current_tag="v0.6.0")
    assert plan.current_branch == "v0.6.0"


def test_apply_refuses_to_merge_a_diverged_branch(tmp_path: Path):
    origin = tmp_path / "origin"
    origin.mkdir()
    _git(origin, "init", "-q", "-b", "main")
    _commit(origin, "a.txt", "a")
    _git(origin, "tag", "v0.5.0")
    work = tmp_path / "work"
    subprocess.run(["git", "clone", "-q", str(origin), str(work)],
                   check=True, capture_output=True, text=True)
    # local commit on main that origin does not have -> pull --ff-only must fail
    _commit(work, "local.txt", "local")
    plan = build_plan(work, target_tag="v0.7.0", current_tag="v0.5.0")
    # a dirty-tracking-free plan can be built, but applying must not create a merge
    _commit(origin, "remote.txt", "remote")
    _git(work, "fetch", "-q", "origin")
    with pytest.raises(UpdateRefused) as excinfo:
        apply_plan(work, plan)
    assert "ff-only" in str(excinfo.value)

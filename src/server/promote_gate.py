# SPDX-License-Identifier: MIT
"""What may leave a staging copy.

One property carries the whole safety model: promotion writes a commit onto a
dedicated branch and executes nothing — no checkout, no hook, no build, no
change to the project's working tree. Everything else here is a supplement.

The deny list below will rot. It is not the control; it is a second pair of
eyes on top of the branch rule.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from pathlib import Path

from src.server.room_stages import git

EXECUTION_SURFACE: tuple[str, ...] = (
    "package.json",
    "Makefile",
    ".env",
    "setup.py",
    "pyproject.toml",
    "conftest.py",
    ".github/workflows/*",
    ".vscode/tasks.json",
    ".vscode/settings.json",
)


@dataclass
class GateVerdict:
    allowed: bool
    reason: str = ""
    paths: list[str] = field(default_factory=list)


def changed_paths(stage_path: str | Path, baseline_ref: str) -> list[str]:
    """Tracked edits plus untracked files, relative to the worktree root."""
    diff = git(stage_path, "diff", "--name-only", "-z", baseline_ref)
    others = git(stage_path, "ls-files", "--others", "--exclude-standard", "-z")
    names: list[str] = []
    for blob in (diff.stdout, others.stdout):
        names.extend(part for part in blob.split("\0") if part)
    return sorted(set(names))


def _normalise(path: str) -> str:
    path = path.replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path


def classify(paths: list[str]) -> GateVerdict:
    for raw in paths:
        path = raw.replace("\\", "/")
        if path.startswith("/") or path == ".." or path.startswith("../"):
            return GateVerdict(False, f"path escapes the staging: {raw}", list(paths))
        if path == ".git" or path.startswith(".git/"):
            return GateVerdict(
                False,
                f"the contribution writes into .git ({raw}); the whole "
                "contribution is refused",
                list(paths),
            )
    for raw in paths:
        path = _normalise(raw)
        for pattern in EXECUTION_SURFACE:
            if path == pattern or fnmatch.fnmatch(path, pattern):
                return GateVerdict(
                    False, f"{raw} is on the execution surface", list(paths),
                )
    return GateVerdict(True, "", list(paths))


def promote(
    project_root: str | Path, stage_path: str | Path, baseline_ref: str,
    branch: str, message: str,
) -> str:
    """Write one commit onto `branch` without touching anything else.

    Plumbing end to end: the worktree's index is filled, a tree is written, a
    commit object is built with `commit-tree`, and a ref on the project is
    pointed at it. Nothing is checked out and no hook can fire.
    """
    added = git(stage_path, "add", "-A")
    if added.returncode != 0:
        raise RuntimeError(f"staging add failed: {added.stderr.strip()}")
    tree = git(stage_path, "write-tree")
    if tree.returncode != 0:
        raise RuntimeError(f"write-tree failed: {tree.stderr.strip()}")
    commit = git(
        stage_path, "commit-tree", tree.stdout.strip(),
        "-p", baseline_ref, "-m", message,
    )
    if commit.returncode != 0:
        raise RuntimeError(f"commit-tree failed: {commit.stderr.strip()}")
    sha = commit.stdout.strip()
    ref = git(project_root, "update-ref", f"refs/heads/{branch}", sha)
    if ref.returncode != 0:
        raise RuntimeError(f"update-ref failed: {ref.stderr.strip()}")
    return sha

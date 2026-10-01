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
import os
import tempfile
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
    ".gitmodules",
    ".envrc",
    "vite.config.*",
    "webpack.config.*",
    "rollup.config.*",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "Jenkinsfile",
    ".gitlab-ci.yml",
    ".circleci/config.yml",
    ".travis.yml",
    ".devcontainer/**",
    ".npmrc",
    ".pypirc",
    ".netrc",
    "*.sh",
    "*.ps1",
    "*.bat",
    "*.cmd",
)

# Git keeps the file kind in the mode, so a path list cannot see any of these.
_REFUSED_MODES = {
    "120000": "a symlink",
    "160000": "a gitlink",
    "100755": "executable",
}


@dataclass
class GateVerdict:
    allowed: bool
    reason: str = ""
    paths: list[str] = field(default_factory=list)


def _mode_refusal(old_mode: str, new_mode: str, raw: str) -> str:
    """The reason this entry may not leave, or an empty string.

    A deletion carries mode 000000 and changes nothing. A new file arrives as
    000000 -> 100644, which is not a mode change either; anything else that
    moves the mode is.
    """
    if new_mode == "000000":
        return ""
    kind = _REFUSED_MODES.get(new_mode)
    if kind is not None:
        return f"{raw} arrives as {kind}; only plain files may leave the staging"
    if new_mode != "100644":
        return f"{raw} has an unexpected file mode ({new_mode})"
    if old_mode not in ("000000", new_mode):
        return f"{raw} changes file mode ({old_mode} -> {new_mode})"
    return ""


def changed_entries(
    stage_path: str | Path, baseline_ref: str,
) -> list[tuple[str, str, str]]:
    """(old_mode, new_mode, path) for everything that differs from the baseline.

    A throwaway index is filled rather than the staging's own, so this stays a
    read. `--name-only` would report neither symlinks nor mode changes: git
    keeps the file kind in the mode field, and a list of names cannot see it.
    `--no-renames` keeps one path per record.
    """
    handle, scratch = tempfile.mkstemp(prefix="fsar-gate-index-")
    os.close(handle)
    os.unlink(scratch)
    env = {"GIT_INDEX_FILE": scratch}
    try:
        added = git(stage_path, "add", "-A", env=env)
        if added.returncode != 0:
            raise RuntimeError(f"staging add failed: {added.stderr.strip()}")
        raw = git(
            stage_path, "diff", "--raw", "--cached", "--no-renames", "-z",
            baseline_ref, env=env,
        )
    finally:
        Path(scratch).unlink(missing_ok=True)

    entries: list[tuple[str, str, str]] = []
    parts = raw.stdout.split("\0")
    index = 0
    while index < len(parts):
        head = parts[index]
        index += 1
        if not head.startswith(":"):
            continue
        fields = head[1:].split(" ")
        path = parts[index] if index < len(parts) else ""
        index += 1
        entries.append((fields[0], fields[1], path))
    return entries


def changed_paths(stage_path: str | Path, baseline_ref: str) -> list[str]:
    """Tracked edits plus untracked files, relative to the worktree root."""
    return sorted({path for _, _, path in changed_entries(stage_path, baseline_ref)})


def _normalise(path: str) -> str:
    path = path.replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path


def classify(entries: list[tuple[str, str, str]]) -> GateVerdict:
    paths = sorted({path for _, _, path in entries})
    for old_mode, new_mode, raw in entries:
        refusal = _mode_refusal(old_mode, new_mode, raw)
        if refusal:
            return GateVerdict(False, refusal, list(paths))
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

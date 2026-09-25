# SPDX-License-Identifier: MIT
"""Plan and run a git update.

The app ships to end users who have no write access to the upstream repo, so
every step here is read-only against the remote: no push, no remote branch
deletion. Old local branches are dropped only when the target branch already
contains them.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from src.utils.logger import logger
from src.utils.version import base_tag, channel_of

_TIMEOUT = 180
_IN_PROGRESS = (
    ("rebase-merge", "rebase"),
    ("rebase-apply", "rebase"),
    ("MERGE_HEAD", "merge"),
    ("CHERRY_PICK_HEAD", "cherry-pick"),
    ("REVERT_HEAD", "revert"),
)


class UpdateRefused(RuntimeError):
    pass


@dataclass(frozen=True)
class UpdatePlan:
    target_tag: str
    target_branch: str
    current_tag: str
    current_branch: str | None
    steps: tuple[tuple[str, ...], ...]
    drop_branch: str | None


def target_branch_for(tag: str) -> str:
    """Stable releases live on main; a beta tag owns a branch named for its
    version (`v0.6.0-beta1` -> `v0.6.0`)."""
    base = base_tag(tag)
    if channel_of(base) == "stable":
        return "main"
    version = base.lstrip("vV").split("-", 1)[0]
    return f"v{version}"


def _run(repo: Path, args: tuple[str, ...], *, config=None) -> tuple[int, str]:
    if config is not None:
        from src.skills.egress import check_command

        decision = check_command("git " + " ".join(args), config)
        if not decision.allowed:
            raise UpdateRefused(f"egress denied: {decision.reason}")
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise UpdateRefused(f"git {' '.join(args)} could not run: {exc}") from exc
    output = (result.stdout + result.stderr).strip()
    return result.returncode, output


def _must(repo: Path, args: tuple[str, ...], *, config=None) -> str:
    code, output = _run(repo, args, config=config)
    if code != 0:
        raise UpdateRefused(f"git {' '.join(args)} failed: {output}")
    return output


def _git_dir(repo: Path, *, config=None) -> Path:
    raw = Path(_must(repo, ("rev-parse", "--git-dir"), config=config))
    return raw if raw.is_absolute() else (repo / raw).resolve()


def _in_progress_operation(repo: Path, *, config=None) -> str | None:
    git_dir = _git_dir(repo, config=config)
    for marker, label in _IN_PROGRESS:
        if (git_dir / marker).exists():
            return label
    return None


def _tracked_modifications(repo: Path, *, config=None) -> list[str]:
    output = _must(repo, ("status", "--porcelain"), config=config)
    return [line for line in output.splitlines() if line and not line.startswith("??")]


def current_branch_of(repo: Path, *, config=None) -> str | None:
    """Current branch name, or None when HEAD is detached.

    Must be `git branch --show-current`: both `rev-parse --abbrev-ref HEAD` and
    `symbolic-ref --short HEAD` answer `heads/<name>` once a tag shadows the
    branch name, which is exactly what a promoted release creates.
    """
    code, out = _run(repo, ("branch", "--show-current"), config=config)
    if code != 0:
        return None
    return out.strip() or None


def _branch_exists(repo: Path, name: str, *, config=None) -> bool:
    code, _ = _run(
        repo, ("rev-parse", "--verify", "--quiet", f"refs/heads/{name}"),
        config=config,
    )
    return code == 0


def build_plan(
    repo: Path,
    *,
    target_tag: str,
    current_tag: str,
    config=None,
) -> UpdatePlan:
    """Validate preconditions and describe the update. Raises UpdateRefused."""
    in_progress = _in_progress_operation(repo, config=config)
    if in_progress:
        raise UpdateRefused(f"{in_progress} in progress; finish it first")

    dirty = _tracked_modifications(repo, config=config)
    if dirty:
        raise UpdateRefused(f"uncommitted changes would be lost: {dirty[0]}")

    current_branch = current_branch_of(repo, config=config)
    if current_branch is None:
        raise UpdateRefused("detached HEAD; check out the release branch first")

    target_branch = target_branch_for(target_tag)

    steps: list[tuple[str, ...]] = [("fetch", "origin", "--tags")]
    if current_branch == target_branch:
        steps.append(("pull", "--ff-only"))
    else:
        steps.append(("fetch", "origin", target_branch))
        if _branch_exists(repo, target_branch, config=config):
            # `checkout <name>` would resolve a same-named tag and detach.
            steps.extend([("switch", target_branch), ("pull", "--ff-only")])
        else:
            steps.append(("checkout", "-b", target_branch, f"origin/{target_branch}"))

    drop_branch = None
    if (
        current_branch != target_branch
        and channel_of(base_tag(current_tag)) == "beta"
    ):
        drop_branch = current_branch

    return UpdatePlan(
        target_tag=target_tag,
        target_branch=target_branch,
        current_tag=current_tag,
        current_branch=current_branch,
        steps=tuple(steps),
        drop_branch=drop_branch,
    )


def apply_plan(repo: Path, plan: UpdatePlan, *, config=None) -> dict:
    """Run the plan. Never force, never merge, never touch the remote."""
    for step in plan.steps:
        _must(repo, step, config=config)

    dropped = None
    kept = None
    if plan.drop_branch and plan.drop_branch != plan.target_branch:
        # Fully-qualified refs: a tag named like the branch would otherwise
        # satisfy this check and let an unmerged branch be deleted.
        code, _ = _run(
            repo,
            (
                "merge-base", "--is-ancestor",
                f"refs/heads/{plan.drop_branch}",
                f"refs/heads/{plan.target_branch}",
            ),
            config=config,
        )
        if code == 0:
            _must(repo, ("branch", "-D", plan.drop_branch), config=config)
            dropped = plan.drop_branch
        else:
            kept = plan.drop_branch
            logger.info(
                f"kept local branch {plan.drop_branch}: not contained in "
                f"{plan.target_branch}"
            )

    head = _must(repo, ("log", "--oneline", "-1"), config=config)
    return {
        "tag": plan.target_tag,
        "branch": plan.target_branch,
        "head": head,
        "dropped_branch": dropped,
        "kept_branch": kept,
    }

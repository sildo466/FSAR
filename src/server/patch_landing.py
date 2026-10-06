# SPDX-License-Identifier: MIT
"""A patch from elsewhere, landing on a branch.

Applied as text first, then judged on the tree it produced. Both steps are
needed: the apply is what a person approved, byte for byte, and the tree is
the only place a symlink or a mode change becomes visible.

Nothing here executes anything. `promote` writes a commit object and moves a
ref; the worktree it was read from is left where it is.
"""

from __future__ import annotations

from typing import Any

from src.memory.workspace import WorkspaceRepo
from src.server.promote_gate import promote, review
from src.server.room_stages import ensure_stage, git, stage_of


def _slug(value: str) -> str:
    """A branch name that `update-ref` will take, whatever the caller sent."""
    kept = "".join(
        c if c.isalnum() or c in "-._" else "-" for c in str(value)
    )
    return kept.strip("-.") or "x"


def _apply(stage_path: Any, patch_text: str) -> str:
    """Empty on success, otherwise why the patch never reached the tree."""
    checked = git(stage_path, "apply", "--check", "-", input=patch_text)
    if checked.returncode != 0:
        detail = (checked.stderr or checked.stdout).strip()
        return f"the patch does not apply: {detail}"
    written = git(stage_path, "apply", "-", input=patch_text)
    if written.returncode != 0:
        detail = (written.stderr or written.stdout).strip()
        return f"the patch could not be written: {detail}"
    return ""


def land_patch(
    *,
    project_root: Any,
    workspaces: WorkspaceRepo,
    room: Any,
    member_ref: str,
    patch_text: str,
    item_key: str | None = None,
) -> tuple[bool, str, str]:
    """Returns (landed, reason, commit_ref)."""
    try:
        workspace = ensure_stage(
            workspaces, project_root, room.id, "agent", member_ref,
        )
    except Exception as exc:
        return False, f"staging failed: {exc}", ""

    stage_row = stage_of(workspaces, room.id, "agent", member_ref)
    baseline = str(stage_row["baseline_ref"]) if stage_row else ""

    refusal = _apply(workspace.root_path, patch_text)
    if refusal:
        return False, refusal, ""

    paths, refusal = review(workspace.root_path, baseline)
    if refusal:
        return False, refusal, ""
    if not paths:
        return False, "the patch changes nothing", ""

    branch = (
        f"fsar/room-{int(room.id)}/{_slug(item_key)}"
        if item_key
        else f"fsar/room-{int(room.id)}/agent-{_slug(member_ref)}"
    )
    try:
        sha = promote(
            project_root, workspace.root_path, baseline, branch,
            f"room {int(room.id)}: {member_ref}",
        )
    except Exception as exc:
        return False, f"promotion failed: {exc}", ""
    return True, "", sha

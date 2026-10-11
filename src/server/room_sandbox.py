# SPDX-License-Identifier: MIT
"""Which workspace a room's chat turns are confined to.

The sandbox is the room's own column, deliberately separate from its project
root: a project has to be a git repository, a sandbox need not be one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

FALLBACK_DIRNAME = "FSAR-workspace"


def default_sandbox(workspace_repo: Any, config: Any) -> Any:
    """The out-of-box sandbox: `workspace.output_dir`, found or created."""
    configured = str(config.get("workspace.output_dir", "") or "").strip()
    root = Path(configured).expanduser() if configured else Path.home() / FALLBACK_DIRNAME
    root.mkdir(parents=True, exist_ok=True)
    return workspace_repo.ensure_root(str(root))


def room_sandbox_for(
    rooms: Any, workspace_repo: Any, config: Any,
) -> Callable[[str], Any | None]:
    """Resolve a conversation id to the sandbox its room is confined to.

    Returns None for anything that is not a room's conversation. Callers read
    that as "this is not a room chat turn", which is what keeps the owner's
    own conversations on their existing policy.

    A bound row that has since been deleted falls back to the default sandbox
    rather than to None: losing the room's boundary must not silently hand the
    turn back to the conversation's own binding.
    """

    def resolve(conv_id: str) -> Any | None:
        room = rooms.get_by_session(conv_id) if conv_id else None
        if room is None:
            return None
        if room.sandbox_workspace_id:
            bound = workspace_repo.get(int(room.sandbox_workspace_id))
            if bound is not None:
                return bound
        return default_sandbox(workspace_repo, config)

    return resolve

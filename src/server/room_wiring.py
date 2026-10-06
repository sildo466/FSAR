# SPDX-License-Identifier: MIT
"""Turning one plan item into a turn, and its diff into a branch.

This is the only place that knows how the pieces fit: the scheduler, the
member's staging, the gate. Keeping it separate from all three means each of
them can be tested without the others.

What lives here is only what the board records. The turn itself owns
`room.work.started` / `room.work.finished`.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from src.memory.room_plan import RoomPlanStore
from src.memory.workspace import WorkspaceRepo
from src.server.promote_gate import promote, review
from src.server.room_stages import ensure_stage, stage_of


def _character_for(group_engine: Any, room: Any, ref: str) -> Any:
    """The owner, resolved against the room's own membership. A ref that is
    not a member is not an owner, whatever the board says."""
    try:
        character_id = int(ref)
    except (TypeError, ValueError):
        return None
    if character_id not in set(group_engine.rooms.members(room.id)):
        return None
    return group_engine.chat.card_repo.get_character(character_id)


def dispatch_item(
    *,
    group_engine: Any,
    rooms: Any,
    plans: RoomPlanStore,
    workspaces: WorkspaceRepo,
    project_root_for: Callable[[Any], Any],
    emit: Callable[[dict], Awaitable[None]],
    cancel: Callable[[int], bool],
    ws: Any = None,
) -> Callable[[Any, Any, Any], Awaitable[None]]:
    async def dispatch(room: Any, item: Any, _workspace: Any) -> None:
        project_root = project_root_for(room)
        if project_root is None:
            await _block(plans, emit, room, item, "this room has no project bound")
            return
        kind = str(getattr(item, "owner_kind", "") or "character")
        ref = str(getattr(item, "owner_ref", "") or "")
        if not ref:
            await _block(plans, emit, room, item, "the item has no owner")
            return
        try:
            workspace = ensure_stage(workspaces, project_root, room.id, kind, ref)
        except Exception as exc:
            await _block(plans, emit, room, item, f"staging failed: {exc}")
            return

        character = _character_for(group_engine, room, ref)
        if character is None:
            await _block(plans, emit, room, item, "the owner is not in the room")
            return

        await group_engine.speak_work(
            ws, room=room, character=character, history=[], item=item,
            should_stop=lambda: cancel(room.id), workspace_override=workspace,
        )

        stage_row = stage_of(workspaces, room.id, kind, ref)
        baseline = str(stage_row["baseline_ref"]) if stage_row else ""
        paths, refusal = review(workspace.root_path, baseline)
        if not paths:
            if not _reported_done(plans, room, item):
                await _block(
                    plans, emit, room, item,
                    "the turn ended without a report or a change",
                )
            return

        if refusal:
            await _block(plans, emit, room, item, refusal)
            await emit({
                "type": "room.promote.rejected", "room_id": room.id,
                "item_key": item.item_key, "reason": refusal,
            })
            return

        await emit({
            "type": "room.promote.requested", "room_id": room.id,
            "item_key": item.item_key, "paths": paths,
        })
        branch = f"fsar/room-{int(room.id)}/{item.item_key}"
        try:
            sha = promote(
                project_root, workspace.root_path, baseline, branch,
                f"room {int(room.id)}: {item.text}",
            )
        except Exception as exc:
            await _block(plans, emit, room, item, f"promotion failed: {exc}")
            return

        plans.set_commit_ref(room.id, item.item_key, sha)
        if not _reported_done(plans, room, item):
            # A diff landed, so the item objectively produced something; the
            # board must not keep calling it unfinished.
            plans.set_status(
                room.id, item.item_key, "done", evidence=f"promoted to {branch}",
            )
        await emit({
            "type": "room.promote.applied", "room_id": room.id,
            "item_key": item.item_key, "commit_ref": sha, "branch": branch,
        })
        await _push_board(plans, emit, room)

    return dispatch


def _reported_done(plans: RoomPlanStore, room: Any, item: Any) -> bool:
    current = plans.get(room.id, item.item_key)
    return current is not None and str(current.status) == "done"


async def _push_board(plans: RoomPlanStore, emit: Any, room: Any) -> None:
    await emit({
        "type": "room.plan.updated", "room_id": room.id,
        "items": [i.to_dict() for i in plans.list(room.id)],
    })


async def _block(
    plans: RoomPlanStore, emit: Any, room: Any, item: Any, reason: str,
) -> None:
    """Mark the item blocked and say why on the board.

    Deliberately not a `room.promote.rejected`: most of the ways to get here
    — no project, no owner, the owner is not a member — never reached the gate
    at all, and reporting them as a refused promotion would misdescribe what
    happened.
    """
    plans.set_status(room.id, item.item_key, "blocked", evidence=reason)
    await _push_board(plans, emit, room)

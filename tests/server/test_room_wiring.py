# SPDX-License-Identifier: MIT
"""Dispatch: a plan item becomes a turn, and its diff becomes a branch."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.memory.room_plan import RoomPlanStore
from src.memory.rooms import RoomStore
from src.memory.session_store import SessionStore
from src.memory.workspace import WorkspaceRepo
from src.server.room_wiring import dispatch_item


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("FSAR_HOME", str(tmp_path / "home"))


def _project(tmp_path, name="project") -> Path:
    root = tmp_path / name
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "t"], check=True)
    (root / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "init"], check=True)
    return root


def _fixture(tmp_path, turn, *, project_root_for=None):
    project = _project(tmp_path)
    db = tmp_path / "memory.db"
    rooms = RoomStore(db, SessionStore(db))
    room = rooms.create(name="R", character_ids=[1], agent_mode=True)
    plans = RoomPlanStore(db)
    plans.replace(room.id, [{
        "id": "a", "text": "add app.py", "status": "todo",
        "owner": {"kind": "character", "ref": "1"},
    }])
    sent: list[dict] = []
    group_engine = SimpleNamespace(
        rooms=SimpleNamespace(members=lambda room_id: [1]),
        chat=SimpleNamespace(card_repo=SimpleNamespace(
            get_character=lambda cid: SimpleNamespace(id=cid, name="Mira"),
        )),
        speak_work=turn,
    )

    async def emit(payload):
        sent.append(payload)

    dispatch = dispatch_item(
        group_engine=group_engine, rooms=rooms, plans=plans,
        workspaces=WorkspaceRepo(db),
        project_root_for=project_root_for or (lambda r: project),
        emit=emit, cancel=lambda room_id: False,
    )
    return SimpleNamespace(
        project=project, rooms=rooms, room=room, plans=plans,
        sent=sent, dispatch=dispatch,
    )


def _run(f, index=0):
    room = f.rooms.get(f.room.id)
    item = f.plans.list(f.room.id)[index]
    asyncio.run(f.dispatch(room, item, None))


def test_the_turn_runs_in_the_members_staging_and_the_diff_is_promoted(tmp_path) -> None:
    written: list[Path] = []

    async def turn(ws, *, room, character, history, item, should_stop,
                   workspace_override=None):
        target = Path(workspace_override.root_path, "app.py")
        target.write_text("print(1)\n", encoding="utf-8")
        written.append(target)
        return "work_1", "done"

    f = _fixture(tmp_path, turn)

    _run(f)

    item = f.plans.list(f.room.id)[0]
    assert written and written[0].exists()
    assert item.commit_ref
    assert item.status == "done"
    assert not (f.project / "app.py").exists()
    assert any(m["type"] == "room.promote.applied" for m in f.sent)


def test_the_turn_is_handed_a_staging_that_is_not_the_project(tmp_path) -> None:
    seen: list[str] = []

    async def turn(ws, *, room, character, history, item, should_stop,
                   workspace_override=None):
        seen.append(workspace_override.root_path)
        return "work_1", "done"

    f = _fixture(tmp_path, turn)

    _run(f)

    assert seen and Path(seen[0]) != f.project


def test_a_contribution_that_touches_the_execution_surface_is_refused(tmp_path) -> None:
    async def turn(ws, *, room, character, history, item, should_stop,
                   workspace_override=None):
        Path(workspace_override.root_path, "package.json").write_text(
            "{}\n", encoding="utf-8",
        )
        return "work_1", "done"

    f = _fixture(tmp_path, turn)

    _run(f)

    item = f.plans.list(f.room.id)[0]
    assert item.status == "blocked"
    assert "package.json" in item.evidence


def test_a_turn_that_changes_nothing_and_reports_nothing_is_blocked(tmp_path) -> None:
    """The turn owns room.work.*; this only owns what the board records. An
    item that produced neither a diff nor a report must not sit in `doing`
    looking like work in progress."""
    async def turn(ws, *, room, character, history, item, should_stop,
                   workspace_override=None):
        return "work_1", "nothing needed doing"

    f = _fixture(tmp_path, turn)

    _run(f)

    item = f.plans.list(f.room.id)[0]
    assert item.commit_ref is None
    assert item.status == "blocked"
    assert not any(m["type"].startswith("room.promote.") for m in f.sent)
    assert not any(m["type"] == "room.work.finished" for m in f.sent)

def test_a_turn_that_reports_done_without_a_diff_stays_done(tmp_path) -> None:
    """An investigation item is a legitimate plan item: no files move, and the
    report is the deliverable."""
    async def turn(ws, *, room, character, history, item, should_stop,
                   workspace_override=None):
        f.plans.set_status(room.id, item.item_key, "done", evidence="read the code")
        return "work_1", "read the code"

    f = _fixture(tmp_path, turn)

    _run(f)

    item = f.plans.list(f.room.id)[0]
    assert item.status == "done"
    assert item.commit_ref is None


def test_a_room_with_no_project_is_blocked_not_crashed(tmp_path) -> None:
    async def turn(ws, *, room, character, history, item, should_stop,
                   workspace_override=None):
        raise AssertionError("must not run without a project")

    f = _fixture(tmp_path, turn, project_root_for=lambda r: None)

    _run(f)

    item = f.plans.list(f.room.id)[0]
    assert item.status == "blocked"
    assert "project" in item.evidence


def test_an_owner_that_is_not_a_member_is_blocked(tmp_path) -> None:
    async def turn(ws, *, room, character, history, item, should_stop,
                   workspace_override=None):
        raise AssertionError("must not run for a non-member")

    f = _fixture(tmp_path, turn)
    f.plans.replace(f.room.id, [{
        "id": "a", "text": "t", "status": "todo",
        "owner": {"kind": "character", "ref": "42"},
    }])

    _run(f)

    item = f.plans.list(f.room.id)[0]
    assert item.status == "blocked"
    assert "not in the room" in item.evidence


def test_the_promote_events_carry_the_branch_and_the_commit(tmp_path) -> None:
    async def turn(ws, *, room, character, history, item, should_stop,
                   workspace_override=None):
        Path(workspace_override.root_path, "app.py").write_text("x\n", encoding="utf-8")
        return "work_1", "done"

    f = _fixture(tmp_path, turn)

    _run(f)

    applied = next(m for m in f.sent if m["type"] == "room.promote.applied")
    assert applied["branch"] == f"fsar/room-{f.room.id}/a"
    assert applied["commit_ref"]
    requested = next(m for m in f.sent if m["type"] == "room.promote.requested")
    assert requested["item_key"] == "a"


def test_the_promoted_branch_really_exists_on_the_project(tmp_path) -> None:
    async def turn(ws, *, room, character, history, item, should_stop,
                   workspace_override=None):
        Path(workspace_override.root_path, "app.py").write_text("x\n", encoding="utf-8")
        return "work_1", "done"

    f = _fixture(tmp_path, turn)

    _run(f)

    branches = subprocess.run(
        ["git", "-C", str(f.project), "branch", "--list", "fsar/*"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert f"fsar/room-{f.room.id}/a" in branches

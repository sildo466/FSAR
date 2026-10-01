# SPDX-License-Identifier: MIT
"""The room.* messages a person settles a patch with."""

from __future__ import annotations

import asyncio
import subprocess
from types import SimpleNamespace

import pytest

from src.memory.patches import PatchStore
from src.memory.workspace import WorkspaceRepo
from src.server.handlers import group as group_handler

PATCH = (
    "diff --git a/app.py b/app.py\n"
    "--- a/app.py\n"
    "+++ b/app.py\n"
    "@@ -1,1 +1,1 @@\n-x = 1\n+x = 2\n"
)


class FakeWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send_json(self, message: dict) -> None:
        self.messages.append(message)


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("FSAR_HOME", str(tmp_path / "home"))


def _project(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "t"], check=True)
    (root / "app.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "init"], check=True)
    return root


def _wire(tmp_path, *, items=None):
    root = _project(tmp_path)
    room = SimpleNamespace(
        id=1, session_id="s1", agent_mode=True, max_rounds=0,
        user_card_id=None, goal="", phase="working", workspace_id=3,
    )
    rooms = SimpleNamespace(
        get=lambda room_id: room if room_id == 1 else None,
        members=lambda room_id: [7],
        update=lambda *a, **kw: room,
        clear_workspace=lambda room_id: room,
    )
    board = {"items": items or []}
    plans = SimpleNamespace(
        list=lambda room_id: [
            SimpleNamespace(to_dict=lambda i=i: dict(i)) for i in board["items"]
        ],
        get=lambda room_id, key: SimpleNamespace(item_key=key, text="t"),
        set_commit_ref=lambda room_id, key, sha: None,
        set_status=lambda room_id, key, state, evidence="": None,
    )
    patches = PatchStore(tmp_path / "memory.db")
    workspaces = WorkspaceRepo(tmp_path / "memory.db")

    async def run_chain(ws, *, room, user_input, mentioned, user_card):
        return "settled"

    engine = SimpleNamespace(
        run_chain=run_chain,
        chat=SimpleNamespace(card_repo=SimpleNamespace(
            get_character=lambda c: None,
            get_user_card=lambda cid: None,
            get_default_user_card=lambda: None,
        )),
    )
    group_handler.set_engine(engine, rooms)
    group_handler.set_room_plan_engine(rooms, plans)
    group_handler.set_room_publish(None, lambda live_room: str(root))
    group_handler.set_room_patch(patches, workspaces)
    group_handler._tasks.clear()
    return room, patches, root


def _queue(patches, room, *, item_key=None) -> int:
    return patches.add(
        room.id, "claude-laptop", patch_text=PATCH, digest="a" * 64,
        size=len(PATCH), item_key=item_key,
    ).id


def _run(ws, msg):
    asyncio.run(group_handler.dispatch(ws, msg))


def test_listing_patches_sends_the_queue_back(tmp_path) -> None:
    room, patches, _root = _wire(tmp_path)
    _queue(patches, room)
    ws = FakeWebSocket()

    _run(ws, {"type": "room.patch.list", "room_id": 1})

    updated = [m for m in ws.messages if m["type"] == "room.patch.updated"]
    assert updated and updated[0]["patches"][0]["state"] == "pending"
    assert "patch_text" not in updated[0]["patches"][0]


def test_the_text_is_sent_on_demand(tmp_path) -> None:
    room, patches, _root = _wire(tmp_path)
    pid = _queue(patches, room)
    ws = FakeWebSocket()

    _run(ws, {"type": "room.patch.text", "room_id": 1, "patch_id": pid})

    sent = [m for m in ws.messages if m["type"] == "room.patch.text"]
    assert sent and sent[0]["patch"] == PATCH


def test_an_unknown_patch_id_is_reported(tmp_path) -> None:
    _room, _patches, _root = _wire(tmp_path)
    ws = FakeWebSocket()

    _run(ws, {"type": "room.patch.text", "room_id": 1, "patch_id": 999})

    err = [m for m in ws.messages if m["type"] == "group.error"]
    assert err and err[0]["code"] == "not_found"


def test_refusing_a_patch_settles_it_without_touching_the_project(tmp_path) -> None:
    room, patches, root = _wire(tmp_path)
    pid = _queue(patches, room)
    ws = FakeWebSocket()

    _run(ws, {"type": "room.patch.decide", "room_id": 1,
              "patch_id": pid, "approve": False})

    assert patches.get(1, pid).state == "rejected"
    assert (root / "app.py").read_text(encoding="utf-8") == "x = 1\n"


def test_approving_a_patch_lands_it_on_a_branch(tmp_path) -> None:
    room, patches, root = _wire(tmp_path)
    pid = _queue(patches, room)
    ws = FakeWebSocket()

    _run(ws, {"type": "room.patch.decide", "room_id": 1,
              "patch_id": pid, "approve": True})

    decided = [m for m in ws.messages if m["type"] == "room.patch.decided"]
    assert decided and decided[0]["state"] == "landed"
    assert len(decided[0]["commit_ref"]) == 40
    assert patches.get(1, pid).state == "landed"
    assert (root / "app.py").read_text(encoding="utf-8") == "x = 1\n"


def test_a_settled_patch_cannot_be_settled_again(tmp_path) -> None:
    room, patches, _root = _wire(tmp_path)
    pid = _queue(patches, room)
    ws = FakeWebSocket()
    _run(ws, {"type": "room.patch.decide", "room_id": 1,
              "patch_id": pid, "approve": False})
    ws.messages.clear()

    _run(ws, {"type": "room.patch.decide", "room_id": 1,
              "patch_id": pid, "approve": True})

    err = [m for m in ws.messages if m["type"] == "group.error"]
    assert err and err[0]["code"] == "not_pending"


def test_a_failing_landing_is_reported_rather_than_hidden(tmp_path) -> None:
    """The patch is checked against the project it was made from; if the
    project moved on, the person is told instead of the patch quietly
    disappearing."""
    room, patches, _root = _wire(tmp_path)
    stale = (
        "diff --git a/app.py b/app.py\n"
        "--- a/app.py\n"
        "+++ b/app.py\n"
        "@@ -1,1 +1,1 @@\n-x = 999\n+x = 2\n"
    )
    pid = patches.add(room.id, "claude-laptop", patch_text=stale,
                      digest="b" * 64, size=len(stale)).id
    ws = FakeWebSocket()

    _run(ws, {"type": "room.patch.decide", "room_id": 1,
              "patch_id": pid, "approve": True})

    decided = [m for m in ws.messages if m["type"] == "room.patch.decided"]
    assert decided and decided[0]["state"] == "rejected"
    assert decided[0]["reason"]

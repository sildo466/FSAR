# SPDX-License-Identifier: MIT
"""A room's chat turns resolve to a sandbox; anything else resolves to nothing."""

from __future__ import annotations

from types import SimpleNamespace

from src.memory.rooms import RoomStore
from src.memory.session_store import SessionStore
from src.memory.workspace import WorkspaceRepo
from src.server.room_sandbox import default_sandbox, room_sandbox_for


def _config(output_dir: str):
    return SimpleNamespace(get=lambda key, default=None: (
        output_dir if key == "workspace.output_dir" else default
    ))


def _parts(tmp_path):
    db = tmp_path / "memory.db"
    session_store = SessionStore(db)
    return RoomStore(db, session_store), WorkspaceRepo(db), session_store


def test_default_sandbox_is_found_or_created_at_output_dir(tmp_path):
    """Finding it twice must not make a second row — the out-of-box seed
    already lives at this path on a normal install."""
    output = tmp_path / "FSAR-workspace"
    _, workspaces, _ = _parts(tmp_path)

    made = default_sandbox(workspaces, _config(str(output)))
    assert made.root_path.endswith("FSAR-workspace")

    again = default_sandbox(workspaces, _config(str(output)))
    assert again.id == made.id
    at_root = [w for w in workspaces.list() if w.root_path == made.root_path]
    assert len(at_root) == 1, "the same root must not create a second workspace"


def test_default_sandbox_makes_the_directory_when_it_is_missing(tmp_path):
    output = tmp_path / "made-up"
    _, workspaces, _ = _parts(tmp_path)

    made = default_sandbox(workspaces, _config(str(output)))
    assert output.exists(), "a sandbox root that is not there yet must be created"


def test_room_turn_resolves_to_its_sandbox_and_others_to_none(tmp_path):
    output = tmp_path / "FSAR-workspace"
    rooms, workspaces, session_store = _parts(tmp_path)
    sandbox = default_sandbox(workspaces, _config(str(output)))
    explicit = workspaces.create(name="proj", root_path=str(tmp_path / "proj"))

    room = rooms.create(name="r", character_ids=[], sandbox_workspace_id=explicit.id)
    resolve = room_sandbox_for(rooms, workspaces, _config(str(output)))

    assert resolve(room.session_id).id == explicit.id, "an explicit sandbox wins"
    assert resolve("not-a-room-session") is None

    rooms.set_sandbox(room.id, None)
    assert resolve(room.session_id).id == sandbox.id, "NULL falls back to output_dir"

    plain = session_store.create(kind="chat")
    assert resolve(plain.id) is None, "a plain conversation is not a room turn"


def test_resolve_falls_back_when_the_bound_workspace_is_gone(tmp_path):
    """A sandbox id pointing at a deleted row must not resolve to None — that
    would silently drop the room back onto its conversation binding."""
    output = tmp_path / "FSAR-workspace"
    rooms, workspaces, _ = _parts(tmp_path)
    sandbox = default_sandbox(workspaces, _config(str(output)))
    room = rooms.create(name="r", character_ids=[], sandbox_workspace_id=999_999)

    resolve = room_sandbox_for(rooms, workspaces, _config(str(output)))
    assert resolve(room.session_id).id == sandbox.id


def test_ws_server_attaches_the_resolver_to_the_shared_engine():
    """Without this the whole policy is inert: the engine would never learn a
    conversation is a room's. Asserted against the source rather than by
    importing ws_server, which builds a real engine against the developer's own
    ~/.fsar and a real MCP manager as a side effect of import."""
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2] / "src/server/ws_server.py"
    ).read_text(encoding="utf-8")
    assert "room_sandbox_for(_group_rooms" in source, "the resolver has to be built here"
    assert "_engine.set_room_sandbox_for(" in source, "and handed to the shared engine"

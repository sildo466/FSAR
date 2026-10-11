# SPDX-License-Identifier: MIT
"""Replay of the 2026-10-10 room 7 incident.

Real ChatEngine, real RoomStore, real WorkspaceRepo; nothing about the policy
is stubbed. What the incident shows is that the boundary was the owner's
allowlist rather than the workspace root: `security.always_allow_paths` held
`C:\\Users\\TANG\\**`, and the room's workspace — inherited from
`default_for_new` — was `C:\\`. Everything was therefore "inside", and 15 of
the incident's audit rows read "path is permanently allowed".
"""

from __future__ import annotations

from pathlib import Path

from src.memory.rooms import RoomStore
from src.server.chat_engine import ChatEngine
from src.server.risk_bridge import RiskBridge
from src.server.room_sandbox import room_sandbox_for
from src.utils.fsar_config import FsarConfig

# The line the room's agent went looking for, moved under the allowlist so the
# test says the same thing on any machine.
HOST_CONFIG_NAME = "fsar.yaml"


def _world(tmp_path: Path, monkeypatch):
    """A real engine wired the way ws_server wires it, isolated to tmp_path."""
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    # ChatEngine builds some stores from the ambient config rather than the one
    # handed to it, and those resolve under Path.home(), so the tree has to be
    # there before the engine is constructed.
    (tmp_path / "home" / ".fsar" / "data").mkdir(parents=True, exist_ok=True)
    db = tmp_path / "memory.db"
    output = tmp_path / "FSAR-workspace"
    private = tmp_path / "private"
    private.mkdir(parents=True, exist_ok=True)
    (private / HOST_CONFIG_NAME).write_text("security: {}\n", encoding="utf-8")

    config = FsarConfig(tmp_path / "fsar.yaml")
    config.patch("memory.sqlite_path", str(db))
    config.patch("workspace.output_dir", str(output))
    # The owner's allowlist covers the whole temp tree, exactly as the affected
    # install's covered the whole home directory.
    config.patch("security.always_allow_paths", [str(tmp_path / "**")])
    config.save()

    engine = ChatEngine(config, RiskBridge())
    rooms = RoomStore(db, engine.session_store)
    engine.set_room_sandbox_for(
        room_sandbox_for(rooms, engine.workspace_repo, config)
    )
    return engine, rooms, private / HOST_CONFIG_NAME


def test_the_incident_read_escalates_instead_of_silently_proceeding(tmp_path, monkeypatch):
    engine, rooms, host_config = _world(tmp_path, monkeypatch)
    room = rooms.create(name="工作小组", character_ids=[], agent_mode=True)

    sandbox = engine.room_sandbox(room.session_id)
    assert sandbox is not None, "a room conversation must resolve to a sandbox"
    assert engine.room_sandbox("not-a-room") is None
    assert engine._turn_workspace(room.session_id).id == sandbox.id

    # Control: the owner's own turn still honours the allowlist, so the test
    # below is not passing because the allowlist went missing.
    own = engine.workspace_gate.validate_path(
        str(host_config), workspace_id=sandbox.id, operation="read",
    )
    assert own.action == "proceed"

    room_verdict = engine.workspace_gate.validate_path(
        str(host_config), workspace_id=sandbox.id, operation="read",
        session_id=room.session_id, conversation_id=room.session_id,
        room_turn=True,
    )
    assert room_verdict.action == "confirm_escape", (
        f"the incident read must ask now, got {room_verdict.action!r}"
    )
    assert "permanently" not in room_verdict.reason
    assert room_verdict.rule_matched == "outside_workspace"

# SPDX-License-Identifier: MIT
"""A LAN member can read the board, because reading is all it can do with it.

P3 dispatches to character cards only, so nothing on this surface ever reports
a plan status back — that endpoint arrives with the members that can be given
work.
"""

from __future__ import annotations

import dataclasses
from types import SimpleNamespace

from src.server.room_app import RoomDeps
from src.server.room_routes import plan_projection


def _item(**over) -> SimpleNamespace:
    base = {
        "item_key": "a", "text": "parse the config", "status": "todo",
        "owner_kind": None, "owner_ref": None, "evidence": "",
        "commit_ref": None, "lease_expires_at": None,
    }
    base.update(over)
    return SimpleNamespace(**base)


def test_room_deps_carries_a_plan_store() -> None:
    names = {f.name for f in dataclasses.fields(RoomDeps)}
    assert "plans" in names
    assert next(f for f in dataclasses.fields(RoomDeps) if f.name == "plans").default is None


def test_the_projection_names_every_item() -> None:
    plans = SimpleNamespace(list=lambda room_id: [
        _item(item_key="a", text="one"),
        _item(item_key="b", text="two", status="done"),
    ])
    assert [row["item_key"] for row in plan_projection(plans, 1)] == ["a", "b"]


def test_the_projection_hides_the_rooms_own_bookkeeping() -> None:
    """The lease in particular: it would tell a member who is working right
    now, which is the room's business, not theirs."""
    plans = SimpleNamespace(list=lambda room_id: [
        _item(owner_ref="7", evidence="secret notes", commit_ref="deadbeef",
              lease_expires_at="2099-01-01T00:00:00"),
    ])
    row = plan_projection(plans, 1)[0]
    assert set(row) == {"item_key", "text", "status", "owner_kind"}


def test_the_projection_survives_a_missing_owner() -> None:
    plans = SimpleNamespace(list=lambda room_id: [_item()])
    assert plan_projection(plans, 1)[0]["owner_kind"] is None


def test_no_plan_store_projects_to_nothing() -> None:
    assert plan_projection(None, 1) == []


def test_the_projection_asks_only_for_this_room() -> None:
    asked: list[int] = []

    def _list(room_id):
        asked.append(room_id)
        return []

    plan_projection(SimpleNamespace(list=_list), 42)
    assert asked == [42]

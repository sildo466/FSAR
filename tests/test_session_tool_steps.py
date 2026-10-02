# SPDX-License-Identifier: MIT
"""A turn's tool calls are stored with its message.

Reloading a room used to lose them: the steps existed only as live events. What
is kept is the tool's name and arguments — never what it returned, because a
tool's output is whatever it read.
"""

from __future__ import annotations

import json

from src.memory.session_store import SessionStore


def _turn(tmp_path) -> tuple[SessionStore, str, int]:
    store = SessionStore(tmp_path / "db.sqlite")
    session = store.create().id
    row_id = store.append_message(session, "assistant", "done")
    assert row_id is not None
    return store, session, int(row_id)


def test_a_turn_keeps_the_tool_calls_it_made(tmp_path) -> None:
    store, session, row_id = _turn(tmp_path)
    steps = [{"callId": "c1", "tool": "read_file", "args": {"path": "a.txt"}}]

    assert store.set_message_tool_steps(row_id, steps) is True

    rows = store.get_session_messages(session)
    assert json.loads(rows[0].tool_steps) == steps


def test_a_message_without_steps_reads_back_empty(tmp_path) -> None:
    store, session, _row_id = _turn(tmp_path)
    assert store.get_session_messages(session)[0].tool_steps == ""


def test_steps_can_be_replaced(tmp_path) -> None:
    store, session, row_id = _turn(tmp_path)
    store.set_message_tool_steps(row_id, [{"callId": "c1", "tool": "a", "args": {}}])
    store.set_message_tool_steps(row_id, [{"callId": "c2", "tool": "b", "args": {}}])

    rows = store.get_session_messages(session)
    assert [s["tool"] for s in json.loads(rows[0].tool_steps)] == ["b"]


def test_regenerating_a_reply_drops_the_steps_it_replaced(tmp_path) -> None:
    store, session, row_id = _turn(tmp_path)
    store.set_message_tool_steps(row_id, [{"callId": "c1", "tool": "a", "args": {}}])

    store.update_message(row_id, "second draft", 7)

    assert store.get_session_messages(session)[0].tool_steps == ""


def test_steps_survive_the_recent_messages_reader(tmp_path) -> None:
    """Both readers feed the same row mapper, so both must select the column."""
    store, session, row_id = _turn(tmp_path)
    store.set_message_tool_steps(row_id, [{"callId": "c1", "tool": "a", "args": {}}])

    recent = store.get_recent_messages(session)
    assert json.loads(recent[0].tool_steps)[0]["tool"] == "a"

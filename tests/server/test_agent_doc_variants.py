# SPDX-License-Identifier: MIT
"""Two documents, because the two rooms offer different things.

A member in a chat-only room can read and speak, and telling it about a plan
board it will never see is the kind of lie the consistency test exists to
prevent. A member in a working room can see the work.
"""

from __future__ import annotations

from src.server.agent_doc import agent_md


def test_a_chat_room_document_promises_reading_and_speaking_only() -> None:
    doc = agent_md(False)
    assert "/room/index" in doc
    assert "16 KiB" in doc
    assert "plan" not in doc.lower()


def test_a_working_room_document_does_not_describe_a_route_that_is_not_there() -> None:
    """A working room's members read the board; nothing on this surface takes
    a change to it."""
    working = agent_md(True)
    assert "/room/index" in working
    assert "/plan/" not in working


def test_the_working_text_describes_the_board() -> None:
    working = agent_md(True)
    assert "plan" in working.lower()
    for field in ("item_key", "text", "status", "owner_kind"):
        assert field in working, field


def test_the_chat_text_still_promises_no_board() -> None:
    """This is where the divergence is recorded: the seat is filled."""
    assert agent_md(True) != agent_md(False)
    assert "plan" not in agent_md(False).lower()

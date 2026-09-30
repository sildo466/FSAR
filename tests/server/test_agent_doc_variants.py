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
    """An agent room's members can do no more than a chat room's until the plan
    board exists. This is the test that changes when it does."""
    working = agent_md(True)
    assert "/room/index" in working
    assert "/plan/" not in working


def test_the_two_texts_are_the_same_for_now() -> None:
    """The seam is in place and nothing more. Inventing a difference now would
    be a promise about the other version, which is the thing the consistency
    test forbids — so this is where the divergence gets recorded, in P3b."""
    assert agent_md(True) == agent_md(False)

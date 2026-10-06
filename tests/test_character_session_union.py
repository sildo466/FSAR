# SPDX-License-Identifier: MIT
from __future__ import annotations

import tempfile
from pathlib import Path

from src.memory.session_store import SessionStore


def _store() -> SessionStore:
    tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    return SessionStore(Path(tmp.name) / "test.db")


def test_bound_session_is_returned_without_speaker_attribution() -> None:
    """Legacy chat behaviour: binding alone is enough, no message attribution."""
    store = _store()
    session = store.create()
    store.set_character(session.id, 7)
    store.append_message(session.id, "assistant", "hello")
    assert session.id in store.session_ids_for_character(7)


def test_unbound_session_with_speaker_attribution_is_returned() -> None:
    """Group behaviour: no binding, but the character spoke there."""
    store = _store()
    session = store.create(kind="group")
    store.append_message(session.id, "assistant", "hello", character_card_id=7)
    assert session.id in store.session_ids_for_character(7)


def test_other_characters_sessions_are_excluded() -> None:
    store = _store()
    mine = store.create(kind="group")
    theirs = store.create(kind="group")
    store.append_message(mine.id, "assistant", "a", character_card_id=7)
    store.append_message(theirs.id, "assistant", "b", character_card_id=8)
    result = store.session_ids_for_character(7)
    assert mine.id in result
    assert theirs.id not in result


def test_user_messages_do_not_attribute_a_session() -> None:
    store = _store()
    session = store.create(kind="group")
    store.append_message(session.id, "user", "hi")
    assert store.session_ids_for_character(7) == []


def test_results_are_deduplicated() -> None:
    store = _store()
    session = store.create(kind="group")
    store.set_character(session.id, 7)
    store.append_message(session.id, "assistant", "a", character_card_id=7)
    store.append_message(session.id, "assistant", "b", character_card_id=7)
    assert store.session_ids_for_character(7).count(session.id) == 1


def test_both_sources_are_combined() -> None:
    store = _store()
    bound = store.create()
    store.set_character(bound.id, 7)
    spoke = store.create(kind="group")
    store.append_message(spoke.id, "assistant", "x", character_card_id=7)
    result = store.session_ids_for_character(7)
    assert set(result) == {bound.id, spoke.id}


def test_unknown_character_has_no_sessions() -> None:
    store = _store()
    store.create()
    assert store.session_ids_for_character(999) == []


def test_removing_speaker_attribution_drops_group_session_scope() -> None:
    """Regenerating or clearing a speaker must not strand memory scope."""
    store = _store()
    session = store.create(kind="group")
    msg_id = store.append_message(
        session.id, "assistant", "a", character_card_id=7,
    )
    store.delete_messages([msg_id])
    assert store.session_ids_for_character(7) == []

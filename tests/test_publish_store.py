# SPDX-License-Identifier: MIT
"""The publish ledger: volume and time, never content."""

from __future__ import annotations

from src.memory.publishes import PublishStore


def _store(tmp_path) -> PublishStore:
    return PublishStore(tmp_path / "memory.db")


def test_a_fresh_room_has_published_nothing(tmp_path) -> None:
    assert _store(tmp_path).list(1) == []
    assert _store(tmp_path).latest(1) is None


def test_a_record_comes_back_with_its_numbers(tmp_path) -> None:
    store = _store(tmp_path)

    record = store.record(
        1, "claude-laptop", path_count=12, byte_count=4096, digest="ab" * 32,
    )

    assert record.room_id == 1
    assert record.member_ref == "claude-laptop"
    assert record.path_count == 12
    assert record.bytes == 4096
    assert record.digest == "ab" * 32
    assert record.created_at


def test_latest_is_the_last_one_recorded(tmp_path) -> None:
    store = _store(tmp_path)
    store.record(1, "a", path_count=1, byte_count=1, digest="")
    second = store.record(1, "a", path_count=2, byte_count=2, digest="")

    assert store.latest(1).id == second.id


def test_ledgers_of_two_rooms_do_not_mix(tmp_path) -> None:
    store = _store(tmp_path)
    store.record(1, "a", path_count=1, byte_count=1, digest="")
    store.record(2, "a", path_count=9, byte_count=9, digest="")

    assert [r.path_count for r in store.list(1)] == [1]
    assert store.latest(2).path_count == 9

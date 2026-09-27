# SPDX-License-Identifier: MIT
"""Addresses that may not reach the LAN listener at all."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.memory.lan_blocklist import LanBlocklist


def _store() -> LanBlocklist:
    tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    return LanBlocklist(Path(tmp.name) / "block.db")


def test_an_unknown_address_is_not_blocked() -> None:
    assert _store().is_blocked("192.168.1.20") is False


def test_add_then_is_blocked() -> None:
    store = _store()
    assert store.add("192.168.1.20", reason="shouting") is True
    assert store.is_blocked("192.168.1.20") is True


def test_adding_twice_reports_false() -> None:
    store = _store()
    store.add("192.168.1.20")
    assert store.add("192.168.1.20") is False
    assert len(store.list()) == 1


def test_remove_reports_whether_it_was_there() -> None:
    store = _store()
    store.add("192.168.1.20")
    assert store.remove("192.168.1.20") is True
    assert store.remove("192.168.1.20") is False
    assert store.is_blocked("192.168.1.20") is False


def test_list_is_newest_first_and_carries_the_reason() -> None:
    store = _store()
    store.add("10.0.0.1", reason="first")
    store.add("10.0.0.2", reason="second")
    rows = store.list()
    assert [row["ip"] for row in rows] == ["10.0.0.2", "10.0.0.1"]
    assert rows[0]["reason"] == "second"


def test_a_blank_address_is_refused() -> None:
    with pytest.raises(ValueError):
        _store().add("   ")


def test_an_address_is_trimmed_before_storing() -> None:
    store = _store()
    store.add("  192.168.1.20  ")
    assert store.is_blocked("192.168.1.20") is True


def test_survives_a_reopen() -> None:
    tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    db = Path(tmp.name) / "block.db"
    LanBlocklist(db).add("192.168.1.20")
    assert LanBlocklist(db).is_blocked("192.168.1.20") is True

# SPDX-License-Identifier: MIT
from __future__ import annotations

import pytest

from src.security.content_guard import ContentGuard, QuarantineItem
from src.security.content_screen import ScreenVerdict


class _FakeConfig:
    def get(self, path, default=None):
        if path == "security.content_screening.enabled":
            return True
        if path == "security.content_screening.threshold":
            return 0.5
        return default

    def get_judge(self):
        return {}

    def get_active_provider(self):
        return {}


class _StubScreener:
    """Flags any text containing the marker word."""

    def __init__(self, verdicts=None):
        self._verdicts = verdicts or {}
        self.calls = []
        self._jev = None

    def screen_batch(self, items, *, kind):
        self.calls.append((dict(items), kind))
        out = {}
        for k, text in items.items():
            if k in self._verdicts:
                out[k] = self._verdicts[k]
            elif "EVIL" in text:
                out[k] = ScreenVerdict(flagged=True, confidence=0.99)
            else:
                out[k] = ScreenVerdict(flagged=False, confidence=0.01)
        return out


class _FakeAdapter:
    def __init__(self, name, items, *, restore_ok=True):
        self.name = name
        self._items = list(items)
        self.removed = []
        self.restored = []
        self._restore_ok = restore_ok

    def enumerate(self):
        return list(self._items)

    def remove(self, item):
        self.removed.append(item.record_ref)
        self._items = [i for i in self._items if i.record_ref != item.record_ref]
        return True

    def restore(self, item, text):
        if not self._restore_ok:
            return False
        self.restored.append((item.record_ref, text))
        return True


@pytest.fixture
def guard(tmp_path):
    return ContentGuard(
        _FakeConfig(), screener=_StubScreener(), db_path=tmp_path / "m.db", autostart=False
    )


def test_scan_quarantines_only_flagged(guard):
    adapter = _FakeAdapter(
        "chunk",
        [
            QuarantineItem("chunk", "1", "EVIL payload", "memory_chunk"),
            QuarantineItem("chunk", "2", "harmless fact", "memory_chunk"),
        ],
    )
    report = guard.scan_all([adapter])
    assert report["scanned"] == 2
    assert report["quarantined"] == 1
    assert report["unavailable"] == 0
    assert adapter.removed == ["1"]
    rows = guard.list_quarantine()
    assert len(rows) == 1
    assert rows[0]["record_ref"] == "1"
    assert rows[0]["text"] == "EVIL payload"


def test_scan_skips_whitelisted_without_calling_screener(guard):
    adapter = _FakeAdapter(
        "chunk", [QuarantineItem("chunk", "1", "EVIL payload", "memory_chunk")]
    )
    guard.add_to_whitelist("EVIL payload", added_by="restore")
    report = guard.scan_all([adapter])
    assert report["quarantined"] == 0
    assert adapter.removed == []
    assert guard.screener.calls == []


def test_scan_counts_unavailable_and_blocks_nothing(guard):
    guard.screener = _StubScreener(
        verdicts={"k0": ScreenVerdict(False, 0.0, unavailable=True)}
    )
    adapter = _FakeAdapter(
        "semantic_doc", [QuarantineItem("semantic_doc", "d1", "any", "semantic_doc")]
    )
    report = guard.scan_all([adapter])
    assert report["unavailable"] == 1
    assert report["quarantined"] == 0
    assert adapter.removed == []
    assert guard.get_report()["unavailable"] == 1


def test_scan_does_not_remove_when_quarantine_write_fails(guard, monkeypatch):
    adapter = _FakeAdapter("chunk", [QuarantineItem("chunk", "1", "EVIL", "memory_chunk")])

    def _boom(*a, **k):
        raise RuntimeError("disk full")

    monkeypatch.setattr(guard, "record", _boom)
    report = guard.scan_all([adapter])
    assert report["quarantined"] == 0
    assert adapter.removed == []


def test_scan_isolates_each_adapter_failure(guard):
    good = _FakeAdapter("chunk", [QuarantineItem("chunk", "1", "EVIL", "memory_chunk")])

    class _Bad:
        name = "card"

        def enumerate(self):
            raise RuntimeError("card repo down")

        def remove(self, item):
            return False

        def restore(self, item, text):
            return False

    report = guard.scan_all([good, _Bad()])
    assert report["quarantined"] == 1
    assert good.removed == ["1"]


def test_scan_groups_by_kind(guard):
    a = _FakeAdapter("chunk", [QuarantineItem("chunk", "1", "x", "memory_chunk")])
    b = _FakeAdapter("card", [QuarantineItem("card", "2", "y", "character_card")])
    guard.scan_all([a, b])
    kinds = sorted(kind for _, kind in guard.screener.calls)
    assert kinds == ["character_card", "memory_chunk"]


def test_scan_has_no_silent_cap(guard):
    items = [
        QuarantineItem("chunk", str(i), f"fact {i}", "memory_chunk") for i in range(45)
    ]
    adapter = _FakeAdapter("chunk", items)
    report = guard.scan_all([adapter])
    assert report["scanned"] == 45
    assert report["total"] == 45


def test_card_quarantine_keeps_row(guard):
    adapter = _FakeAdapter(
        "card",
        [
            QuarantineItem(
                "card",
                "3",
                "EVIL persona text",
                "character_card",
                original_fields={"description": "EVIL persona text", "personality": "p"},
            )
        ],
    )
    guard.scan_all([adapter])
    row = guard.list_quarantine()[0]
    assert row["store"] == "card"
    assert row["original_fields"]["description"] == "EVIL persona text"


def test_restore_writes_back_and_whitelists(guard):
    adapter = _FakeAdapter(
        "chunk", [QuarantineItem("chunk", "1", "EVIL payload", "memory_chunk")]
    )
    guard.scan_all([adapter])
    qid = guard.list_quarantine()[0]["id"]
    assert guard.restore(qid, [adapter]) is True
    assert adapter.restored == [("1", "EVIL payload")]
    assert guard.is_whitelisted("EVIL payload") is True
    assert guard.list_quarantine() == []


def test_restore_is_a_noop_when_store_write_fails(guard):
    adapter = _FakeAdapter(
        "chunk", [QuarantineItem("chunk", "1", "EVIL", "memory_chunk")], restore_ok=False
    )
    guard.scan_all([adapter])
    qid = guard.list_quarantine()[0]["id"]
    assert guard.restore(qid, [adapter]) is False
    assert guard.is_whitelisted("EVIL") is False
    assert len(guard.list_quarantine()) == 1

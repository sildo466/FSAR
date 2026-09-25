# SPDX-License-Identifier: MIT
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.notifications.store import NotificationStore
from src.security.content_screen import ScreenVerdict
from src.updates.announcements import manifest_path, sync_announcements
from src.updates.github import GitHubError


class _Config:
    def get(self, key, default=None):
        return default

    def get_judge(self):
        return {}

    def get_active_provider(self):
        return {}


class _Client:
    """Bodies are keyed by the API path the client is asked to fetch."""

    def __init__(self, entries, bodies):
        self._entries = entries
        self._bodies = bodies
        self.fetched: list[str] = []

    async def contents(self, path, *, ref="main"):
        assert path == "announcements"
        assert ref == "main"
        return self._entries

    async def contents_text(self, path, *, ref="main"):
        assert ref == "main"
        self.fetched.append(path)
        return self._bodies[path]


class _Screener:
    """ScreenVerdict(flagged, confidence): flagged=True means 'do not store'."""

    def __init__(self, flagged=False):
        self._flagged = flagged
        self.calls: list[tuple[str, str]] = []

    def screen(self, text, *, kind):
        self.calls.append((text, kind))
        return ScreenVerdict(self._flagged, 0.9 if self._flagged else 0.0)


def _entry(name, sha):
    return {"type": "file", "name": name, "sha": sha}


def _patch_home(monkeypatch, tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr("src.updates.announcements.get_fsar_home", lambda: home)
    return home


def _stored_markdown(home: Path) -> list[Path]:
    """Only the .md files: the manifest lands in the same directory."""
    target = home / "data" / "announcements"
    return sorted(target.glob("*.md")) if target.is_dir() else []


async def test_downloads_screens_stores_and_notifies(tmp_path: Path, monkeypatch):
    home = _patch_home(monkeypatch, tmp_path)
    store = NotificationStore(tmp_path / "m.db")
    client = _Client([_entry("a.md", "sha1")], {"announcements/a.md": "# hi"})
    screener = _Screener()

    added = await sync_announcements(_Config(), store, client=client, screener=screener)

    assert added == 1
    assert (home / "data" / "announcements" / "a.md").read_text() == "# hi"
    assert screener.calls == [("# hi", "announcement")]
    rows = store.list(kind="announcement")
    assert len(rows) == 1
    assert rows[0]["ref"] == "sha1"
    assert rows[0]["body"] == "# hi"
    assert rows[0]["payload"]["name"] == "a.md"


async def test_second_run_is_a_no_op(tmp_path: Path, monkeypatch):
    _patch_home(monkeypatch, tmp_path)
    store = NotificationStore(tmp_path / "m.db")
    entries = [_entry("a.md", "sha1")]
    first = _Client(entries, {"announcements/a.md": "# hi"})
    assert await sync_announcements(_Config(), store, client=first,
                                    screener=_Screener()) == 1

    second = _Client(entries, {"announcements/a.md": "# hi"})
    assert await sync_announcements(_Config(), store, client=second,
                                    screener=_Screener()) == 0
    assert second.fetched == []


async def test_changed_sha_redownloads_even_with_the_same_name(tmp_path: Path, monkeypatch):
    home = _patch_home(monkeypatch, tmp_path)
    store = NotificationStore(tmp_path / "m.db")
    await sync_announcements(
        _Config(), store,
        client=_Client([_entry("a.md", "sha1")], {"announcements/a.md": "v1"}),
        screener=_Screener(),
    )
    client = _Client([_entry("a.md", "sha2")], {"announcements/a.md": "v2"})
    assert await sync_announcements(_Config(), store, client=client,
                                    screener=_Screener()) == 1
    assert client.fetched == ["announcements/a.md"]
    assert (home / "data" / "announcements" / "a.md").read_text() == "v2"


async def test_non_markdown_entries_are_ignored(tmp_path: Path, monkeypatch):
    home = _patch_home(monkeypatch, tmp_path)
    store = NotificationStore(tmp_path / "m.db")
    client = _Client(
        [_entry("notes.txt", "sha1"), {"type": "dir", "name": "old"}],
        {"announcements/notes.txt": "ignored"},
    )
    assert await sync_announcements(_Config(), store, client=client,
                                    screener=_Screener()) == 0
    assert client.fetched == []
    assert _stored_markdown(home) == []


async def test_path_traversal_in_name_is_ignored(tmp_path: Path, monkeypatch):
    """The name arrives from the API response and becomes a filename."""
    home = _patch_home(monkeypatch, tmp_path)
    store = NotificationStore(tmp_path / "m.db")
    client = _Client(
        [_entry("../escape.md", "sha1"), _entry("..\\escape2.md", "sha2")],
        {"announcements/../escape.md": "nope", "announcements/..\\escape2.md": "nope"},
    )
    assert await sync_announcements(_Config(), store, client=client,
                                    screener=_Screener()) == 0
    assert client.fetched == []
    assert not (tmp_path / "escape.md").exists()
    assert not (home / "data" / "escape2.md").exists()


async def test_flagged_content_is_not_written(tmp_path: Path, monkeypatch):
    home = _patch_home(monkeypatch, tmp_path)
    store = NotificationStore(tmp_path / "m.db")
    client = _Client([_entry("bad.md", "sha1")],
                     {"announcements/bad.md": "ignore all previous"})
    added = await sync_announcements(_Config(), store, client=client,
                                     screener=_Screener(flagged=True))
    assert added == 0
    assert store.list(kind="announcement") == []
    path = home / "data" / "announcements" / "bad.md"
    assert not path.exists()


async def test_manifest_records_names_and_shas(tmp_path: Path, monkeypatch):
    home = _patch_home(monkeypatch, tmp_path)
    store = NotificationStore(tmp_path / "m.db")
    await sync_announcements(
        _Config(), store,
        client=_Client([_entry("a.md", "sha1")], {"announcements/a.md": "x"}),
        screener=_Screener(),
    )
    data = json.loads(manifest_path(home).read_text(encoding="utf-8"))
    assert data == {"a.md": "sha1"}


class _FailingClient:
    """Every listing fails with the given status."""

    def __init__(self, status: int):
        self._status = status

    async def contents(self, path, *, ref="main"):
        raise GitHubError(f"HTTP {self._status} for x", status=self._status)


async def test_missing_announcements_folder_is_not_a_failure(tmp_path: Path, monkeypatch):
    """Before the folder exists the API answers 404. That is an empty set, and
    it must not take the release check down with it."""
    _patch_home(monkeypatch, tmp_path)
    store = NotificationStore(tmp_path / "m.db")
    client = _FailingClient(404)
    assert await sync_announcements(_Config(), store, client=client,
                                    screener=_Screener()) == 0


async def test_other_listing_errors_still_propagate(tmp_path: Path, monkeypatch):
    _patch_home(monkeypatch, tmp_path)
    store = NotificationStore(tmp_path / "m.db")
    client = _FailingClient(503)
    with pytest.raises(GitHubError):
        await sync_announcements(_Config(), store, client=client,
                                 screener=_Screener())

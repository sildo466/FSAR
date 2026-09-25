# SPDX-License-Identifier: MIT
from __future__ import annotations

from pathlib import Path

from src.notifications.store import NotificationStore
from src.updates.releases import select_releases, sync_release_notifications


def _rel(tag, prerelease=False, draft=False, name=None, body="notes"):
    return {
        "tag_name": tag,
        "prerelease": prerelease,
        "draft": draft,
        "name": name or f"FSAR {tag}",
        "body": body,
        "html_url": f"https://github.com/sildo466/FSAR/releases/tag/{tag}",
    }


CURRENT = "v0.6.0-beta1-36-g05eaafd"


def test_skips_older_and_equal_versions():
    picked = select_releases(
        [_rel("v0.5.0"), _rel("v0.6.0-beta1")],
        current_tag=CURRENT, channel="beta", include_prerelease=True,
    )
    assert picked == []


def test_skips_drafts():
    picked = select_releases(
        [_rel("v0.7.0", draft=True)],
        current_tag=CURRENT, channel="beta", include_prerelease=True,
    )
    assert picked == []


def test_beta_channel_receives_both_tracks():
    picked = select_releases(
        [_rel("v0.7.0"), _rel("v0.7.0-beta1", prerelease=True)],
        current_tag=CURRENT, channel="beta", include_prerelease=False,
    )
    assert [r["tag_name"] for r in picked] == ["v0.7.0-beta1", "v0.7.0"]


def test_stable_channel_skips_prerelease_by_default():
    picked = select_releases(
        [_rel("v0.7.0"), _rel("v0.7.0-beta1", prerelease=True)],
        current_tag="v0.6.0", channel="stable", include_prerelease=False,
    )
    assert [r["tag_name"] for r in picked] == ["v0.7.0"]


def test_stable_channel_includes_prerelease_when_opted_in():
    picked = select_releases(
        [_rel("v0.7.0"), _rel("v0.7.0-beta1", prerelease=True)],
        current_tag="v0.6.0", channel="stable", include_prerelease=True,
    )
    assert [r["tag_name"] for r in picked] == ["v0.7.0-beta1", "v0.7.0"]


def test_returns_oldest_first():
    picked = select_releases(
        [_rel("v0.9.0"), _rel("v0.7.0"), _rel("v0.8.0")],
        current_tag=CURRENT, channel="beta", include_prerelease=True,
    )
    assert [r["tag_name"] for r in picked] == ["v0.7.0", "v0.8.0", "v0.9.0"]


def test_unparseable_tag_is_skipped():
    picked = select_releases(
        [_rel("unknown"), _rel("v0.7.0")],
        current_tag=CURRENT, channel="beta", include_prerelease=True,
    )
    assert [r["tag_name"] for r in picked] == ["v0.7.0"]


def test_sync_inserts_one_notification_per_release(tmp_path: Path):
    store = NotificationStore(tmp_path / "m.db")
    added = sync_release_notifications(
        store,
        [_rel("v0.7.0"), _rel("v0.7.0-beta1", prerelease=True)],
        current_tag=CURRENT, channel="beta", include_prerelease=False,
    )
    assert added == 2
    rows = store.list(kind="release")
    refs = {row["ref"] for row in rows}
    assert refs == {"v0.7.0", "v0.7.0-beta1"}


def test_sync_records_channel_and_updatable_in_payload(tmp_path: Path):
    store = NotificationStore(tmp_path / "m.db")
    sync_release_notifications(
        store, [_rel("v0.7.0-beta1", prerelease=True)],
        current_tag=CURRENT, channel="beta", include_prerelease=False,
    )
    payload = store.list(kind="release")[0]["payload"]
    assert payload["tag"] == "v0.7.0-beta1"
    assert payload["channel"] == "beta"
    assert payload["updatable"] is True


def test_sync_is_idempotent(tmp_path: Path):
    store = NotificationStore(tmp_path / "m.db")
    releases = [_rel("v0.7.0")]
    assert sync_release_notifications(
        store, releases, current_tag=CURRENT, channel="beta", include_prerelease=False
    ) == 1
    assert sync_release_notifications(
        store, releases, current_tag=CURRENT, channel="beta", include_prerelease=False
    ) == 0
    assert len(store.list(kind="release")) == 1


def test_sync_stores_the_release_note_as_body(tmp_path: Path):
    store = NotificationStore(tmp_path / "m.db")
    sync_release_notifications(
        store, [_rel("v0.7.0", body="### Highlights\n- group chat")],
        current_tag=CURRENT, channel="beta", include_prerelease=False,
    )
    assert "group chat" in store.list(kind="release")[0]["body"]

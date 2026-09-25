# SPDX-License-Identifier: MIT
"""Turn GitHub releases into feed entries.

One notification per release, so a user who skipped several versions can read
each release note instead of only the newest.
"""

from __future__ import annotations

from functools import cmp_to_key

from src.utils.version import base_tag, channel_of, compare_tags, parse_tag


def select_releases(
    releases: list[dict],
    *,
    current_tag: str,
    channel: str,
    include_prerelease: bool,
) -> list[dict]:
    """Releases newer than `current_tag` that this channel should hear about,
    oldest first."""
    picked: list[tuple[str, dict]] = []
    for release in releases:
        if release.get("draft"):
            continue
        tag = str(release.get("tag_name") or "")
        if parse_tag(tag) is None:
            continue
        order = compare_tags(tag, current_tag)
        if order is None or order <= 0:
            continue
        if release.get("prerelease") and channel != "beta" and not include_prerelease:
            continue
        picked.append((tag, release))
    # Sorting on the numeric tuple alone would tie v0.7.0 with v0.7.0-beta1 and
    # leave them in whatever order the API returned.
    picked.sort(key=cmp_to_key(lambda left, right: compare_tags(left[0], right[0]) or 0))
    return [release for _, release in picked]


def sync_release_notifications(
    store,
    releases: list[dict],
    *,
    current_tag: str,
    channel: str,
    include_prerelease: bool,
) -> int:
    """Insert one notification per new release. Returns how many were added."""
    added = 0
    for release in select_releases(
        releases,
        current_tag=current_tag,
        channel=channel,
        include_prerelease=include_prerelease,
    ):
        tag = str(release["tag_name"])
        inserted = store.add(
            kind="release",
            title=str(release.get("name") or tag),
            body=str(release.get("body") or ""),
            ref=tag,
            url=str(release.get("html_url") or ""),
            payload={
                "tag": tag,
                "base": base_tag(tag),
                "channel": channel_of(tag),
                "updatable": True,
            },
        )
        if inserted is not None:
            added += 1
    return added

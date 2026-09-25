# SPDX-License-Identifier: MIT
"""Mirror the repository's announcements folder into the local feed.

Detection compares blob shas rather than file names: an edited announcement
keeps its name, so a name-only diff would never pick up the revision.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.notifications.store import NotificationStore
from src.utils.fsar_home import get_fsar_home
from src.utils.logger import logger

ANNOUNCEMENTS_DIR = "announcements"
ANNOUNCEMENTS_REF = "main"
_MANIFEST = "manifest.json"


def manifest_path(home: Path | None = None) -> Path:
    return (home or get_fsar_home()) / "data" / ANNOUNCEMENTS_DIR / _MANIFEST


def _local_dir(home: Path | None = None) -> Path:
    return (home or get_fsar_home()) / "data" / ANNOUNCEMENTS_DIR


def _load_manifest(target_dir: Path) -> dict[str, str]:
    path = target_dir / _MANIFEST
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_manifest(target_dir: Path, manifest: dict[str, str]) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / _MANIFEST).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _default_screener(config):
    from src.security.content_screen import ContentScreener

    return ContentScreener(config)


async def sync_announcements(
    config,
    store: NotificationStore,
    *,
    client,
    screener=None,
) -> int:
    """Fetch new or revised announcements. Returns how many were added."""
    entries = await client.contents(ANNOUNCEMENTS_DIR, ref=ANNOUNCEMENTS_REF)
    target_dir = _local_dir()
    manifest = _load_manifest(target_dir)
    screen = screener if screener is not None else _default_screener(config)

    added = 0
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("type") != "file":
            continue
        name = str(entry.get("name") or "")
        # `name` comes from the API response, so keep it a plain basename: a
        # crafted entry must not be able to write outside the announcements dir.
        # Separators are checked explicitly because `Path(name).name` only
        # splits on the host platform's separator.
        if (
            not name.endswith(".md")
            or name.startswith(".")
            or "/" in name
            or "\\" in name
        ):
            continue
        sha = str(entry.get("sha") or "")
        url = str(entry.get("download_url") or "")
        if not sha or not url:
            continue
        local = target_dir / name
        if manifest.get(name) == sha and local.is_file():
            continue

        text = await client.raw(url)
        verdict = screen.screen(text, kind="announcement")
        if verdict.flagged:
            logger.warning(f"announcement {name} screened out; not stored")
            continue

        target_dir.mkdir(parents=True, exist_ok=True)
        local.write_text(text, encoding="utf-8")
        manifest[name] = sha
        inserted = store.add(
            kind="announcement",
            title=name,
            body=text,
            ref=sha,
            payload={"name": name, "sha": sha},
        )
        if inserted is not None:
            added += 1

    _save_manifest(target_dir, manifest)
    return added

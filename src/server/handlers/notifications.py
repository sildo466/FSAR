# SPDX-License-Identifier: MIT
"""WS dispatcher for the notification center."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import WebSocket

from src.notifications.store import KINDS, NotificationStore
from src.updates.apply import UpdateRefused, apply_plan, build_plan
from src.utils.logger import logger


def _store(config: Any) -> NotificationStore:
    path = config.get("memory.sqlite_path") if config is not None else None
    if not path:
        from src.utils.fsar_home import get_fsar_home

        path = get_fsar_home() / "data" / "memory.db"
    return NotificationStore(Path(path))


def _settings(config: Any) -> dict:
    get = (lambda key, default: config.get(key, default)) if config else (
        lambda key, default: default
    )
    return {
        "review": {"enabled": bool(get("notifications.review.enabled", True))},
        "release": {
            "enabled": bool(get("notifications.release.enabled", True)),
            "include_prerelease": bool(
                get("notifications.release.include_prerelease", False)
            ),
        },
        "announcement": {
            "enabled": bool(get("notifications.announcement.enabled", True))
        },
    }


async def _push_state(
    ws: WebSocket,
    store: NotificationStore,
    *,
    marked: list[int] | None = None,
    cleared: bool = False,
) -> None:
    """Report the new state plus exactly which ids changed.

    The ids matter: the client marks only those read, so expanding one item
    does not silently clear the rest of the feed.
    """
    await ws.send_json(
        {
            "type": "notifications.read_result",
            "unread": store.unread_count(),
            "ids": marked or [],
            "cleared": cleared,
        }
    )


async def run_update_checks(config, store, *, client=None, screener=None) -> dict:
    """Discover new releases and announcements. Returns counts.

    Shared by the startup task and the manual `updates.check` message so the
    logic exists in exactly one place.

    The two channels are checked independently: they are separate network calls,
    so a rate limit or an outage on one must not discard what the other found.
    """
    from src.updates.announcements import sync_announcements
    from src.updates.github import GitHubClient
    from src.updates.releases import sync_release_notifications
    from src.utils.version import app_version

    version = app_version()
    counts = {"added": 0, "announcements": 0}
    errors: list[str] = []

    if bool(config.get("notifications.release.enabled", True)):
        try:
            api = client or GitHubClient(config)
            rows = await api.releases()
            counts["added"] = sync_release_notifications(
                store,
                rows,
                current_tag=version["tag"],
                channel=version["channel"],
                include_prerelease=bool(
                    config.get("notifications.release.include_prerelease", False)
                ),
            )
        except Exception as exc:
            errors.append(f"releases: {exc}")

    if bool(config.get("notifications.announcement.enabled", True)):
        try:
            api = client or GitHubClient(config)
            counts["announcements"] = await sync_announcements(
                config, store, client=api, screener=screener
            )
        except Exception as exc:
            errors.append(f"announcements: {exc}")

    if errors:
        counts["error"] = "; ".join(errors)
    return counts


async def dispatch(ws: WebSocket, msg: dict[str, Any], config: Any = None) -> bool:
    t = msg.get("type")
    if t == "notifications.list":
        store = _store(config)
        await ws.send_json(
            {
                "type": "notifications.list_result",
                "items": store.list(),
                "unread": store.unread_count(),
                "kinds": list(KINDS),
                "settings": _settings(config),
            }
        )
        return True
    if t == "notifications.mark_read":
        store = _store(config)
        raw = msg.get("ids")
        ids = [int(item) for item in raw] if isinstance(raw, list) else None
        marked = store.unread_ids(ids)
        store.mark_read(marked)
        await _push_state(ws, store, marked=marked)
        return True
    if t == "notifications.clear":
        store = _store(config)
        store.clear()
        await _push_state(ws, store, cleared=True)
        return True
    if t == "updates.check":
        store = _store(config)
        try:
            counts = await run_update_checks(config, store)
        except Exception as exc:
            logger.warning(f"update check failed: {exc}")
            counts = {"added": 0, "announcements": 0, "error": str(exc)}
        await ws.send_json({"type": "updates.check_result", **counts})
        return True
    if t == "updates.apply":
        tag = str(msg.get("tag") or "")
        if not tag:
            await ws.send_json(
                {"type": "updates.apply_result", "ok": False, "error": "tag is required"}
            )
            return True
        from src.utils.version import app_version, repo_root

        version = app_version()
        try:
            plan = build_plan(
                repo_root(), target_tag=tag, current_tag=version["tag"], config=config
            )
            result = apply_plan(repo_root(), plan, config=config)
            await ws.send_json({"type": "updates.apply_result", "ok": True, **result})
        except UpdateRefused as exc:
            await ws.send_json(
                {"type": "updates.apply_result", "ok": False, "error": str(exc)}
            )
        except Exception as exc:
            logger.warning(f"update apply failed: {exc}")
            await ws.send_json(
                {"type": "updates.apply_result", "ok": False, "error": str(exc)}
            )
        return True
    return False

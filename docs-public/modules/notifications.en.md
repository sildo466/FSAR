# notifications — the notification feed

> Language: [中文](notifications.md) | English · Back to [module index](README.en.md)

One SQLite table (`notifications`) holding four `KINDS`: `review` (a quarantined memory awaiting a decision), `release` (a newer GitHub release, carrying that release's own notes), `announcement` (an official announcement pulled from this repository), and `birthday`. `store.py` (`NotificationStore`) is the only writer; `on_feed_changed` lets the server push a live update, so the sidebar dot lights up wherever a notification was written. The screen is `frontend/src/pages/Notifications.tsx`, reached through `handlers/notifications.py` — which also drives the update flow into [`updates`](updates.en.md).

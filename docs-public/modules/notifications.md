# notifications — 通知流

> 语言：中文 | [English](notifications.en.md) · 返回[模块介绍](README.md)

一张 SQLite 表（`notifications`），四种 `KINDS`：`review`（一条等待你决定的隔离记忆）、`release`（一个更新的 GitHub 版本，带着它自己的说明）、`announcement`（从本仓库拉取的官方公告）、`birthday`。`store.py`（`NotificationStore`）是唯一的写入方；`on_feed_changed` 让服务端推送实时更新，因此无论通知从哪里写入，侧栏小红点都会亮起。界面是 `frontend/src/pages/Notifications.tsx`，经 `handlers/notifications.py` 到达——该 handler 也把更新流程接到 [`updates`](updates.md)。

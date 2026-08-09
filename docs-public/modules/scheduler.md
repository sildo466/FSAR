# scheduler — 定时任务

> 语言：中文 | [English](scheduler.en.md) · 返回 [模块索引](README.md)

基于 APScheduler。`service.py`（`SchedulerService`：生命周期 + 触发分发，经 `core.event_bus` 发事件）、`executor.py`、`delivery.py`、`store.py`（`scheduler.db`）、`triggers.py`、`seed.py` 及自带迁移。GUI 经 `handlers/scheduler.py`（挂载于 `/ws/scheduler`）访问。

# scheduler — scheduled tasks

> Language: [中文](scheduler.md) | English · Back to [module index](README.en.md)

APScheduler-based. `service.py` (`SchedulerService`: lifecycle + trigger dispatch, emitting through `core.event_bus`), `executor.py`, `delivery.py`, `store.py` (`scheduler.db`), `triggers.py`, `seed.py`, plus its own migrations. The GUI reaches it via `handlers/scheduler.py` (mounted at `/ws/scheduler`).

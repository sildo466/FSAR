from datetime import datetime, timezone, timedelta

import pytest

from src.scheduler.types import ScheduleKind, ScheduledJob
from src.scheduler.triggers import build_trigger, parse_interval, next_fire_at


def _job(kind: ScheduleKind, expr: str, tz: str = "") -> ScheduledJob:
    now = datetime.now(timezone.utc)
    return ScheduledJob(
        id=1, name="t", description="", enabled=True,
        schedule_kind=kind, schedule_expr=expr, timezone=tz,
        job_kind=__import__("src.scheduler.types", fromlist=["JobKind"]).JobKind.SYSTEM,
        prompt="", tools_allow="", model_override="", timeout_seconds=60,
        delivery_mode=__import__("src.scheduler.types", fromlist=["DeliveryMode"]).DeliveryMode.DB_ONLY,
        delivery_target="", running_at=None, last_run_at=None,
        last_status=None, last_error="", consecutive_errors=0,
        created_at=now, updated_at=now,
    )


def test_parse_interval_minutes():
    assert parse_interval("30m") == timedelta(minutes=30)


def test_parse_interval_hours():
    assert parse_interval("2h") == timedelta(hours=2)


def test_parse_interval_compound():
    assert parse_interval("1d12h") == timedelta(days=1, hours=12)


def test_parse_interval_invalid():
    with pytest.raises(ValueError):
        parse_interval("not-a-duration")


def test_build_trigger_cron_returns_trigger():
    from apscheduler.triggers.cron import CronTrigger
    t = build_trigger(_job(ScheduleKind.CRON, "0 9 * * *"))
    assert isinstance(t, CronTrigger)


def test_build_trigger_interval_returns_trigger():
    from apscheduler.triggers.interval import IntervalTrigger
    t = build_trigger(_job(ScheduleKind.INTERVAL, "30m"))
    assert isinstance(t, IntervalTrigger)


def test_build_trigger_at_returns_trigger():
    from apscheduler.triggers.date import DateTrigger
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    t = build_trigger(_job(ScheduleKind.AT, future))
    assert isinstance(t, DateTrigger)


def test_build_trigger_startup_returns_none():
    assert build_trigger(_job(ScheduleKind.STARTUP, "")) is None


def test_build_trigger_cron_invalid_raises():
    with pytest.raises(Exception):
        build_trigger(_job(ScheduleKind.CRON, "not-a-cron"))


def test_next_fire_at_cron_future():
    job = _job(ScheduleKind.CRON, "0 9 * * *")
    nxt = next_fire_at(job, datetime.now(timezone.utc))
    assert nxt is not None
    assert nxt > datetime.now(timezone.utc)
"""APScheduler trigger construction + interval parsing.

`build_trigger` returns an APScheduler trigger for cron/interval/at jobs.
STARTUP jobs are handled separately by the service (one-shot add_job with
run_once=True), so this returns None for them.

`parse_interval` accepts a compact format: '30m' / '2h' / '1d12h' / '90s'.
Used by both INTERVAL triggers and STARTUP delay computation.

`next_fire_at` returns the next wall-clock fire time for UI display.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

if TYPE_CHECKING:
    from apscheduler.triggers.base import BaseTrigger

    from src.scheduler.types import ScheduledJob


_INTERVAL_RE = re.compile(r"(\d+)(s|m|h|d)")
_INTERVAL_UNIT = {
    "s": timedelta(seconds=1),
    "m": timedelta(minutes=1),
    "h": timedelta(hours=1),
    "d": timedelta(days=1),
}


def parse_interval(expr: str) -> timedelta:
    """Parse '30m' / '2h' / '1d12h' / '90s' / '1d2h30m' into a timedelta."""
    if not expr:
        raise ValueError("empty interval expression")
    total = timedelta()
    matched = False
    for m in _INTERVAL_RE.finditer(expr):
        matched = True
        n = int(m.group(1))
        unit = _INTERVAL_UNIT[m.group(2)]
        total += n * unit
    if not matched:
        raise ValueError(
            f"invalid interval expression: {expr!r} "
            f"(expected formats: '30m', '2h', '1d12h', '90s')"
        )
    return total


def parse_at(expr: str, tz_name: str = "") -> datetime:
    """Parse an 'at' timestamp into an aware datetime.

    A naive timestamp is interpreted in `tz_name`, falling back to the host's
    local timezone — matching what a user typing '2026-08-09T14:23:00' means.
    """
    target = datetime.fromisoformat(expr)
    if target.tzinfo is not None:
        return target
    if tz_name:
        try:
            from zoneinfo import ZoneInfo
            return target.replace(tzinfo=ZoneInfo(tz_name))
        except Exception:
            pass
    return target.astimezone()


def build_trigger(job: "ScheduledJob") -> "BaseTrigger | None":
    from src.scheduler.types import ScheduleKind

    if job.schedule_kind == ScheduleKind.STARTUP:
        return None

    tz = job.timezone or None

    if job.schedule_kind == ScheduleKind.CRON:
        return CronTrigger.from_crontab(job.schedule_expr, timezone=tz)

    if job.schedule_kind == ScheduleKind.INTERVAL:
        delta = parse_interval(job.schedule_expr)
        return IntervalTrigger(
            seconds=delta.total_seconds(),
            timezone=tz,
        )

    if job.schedule_kind == ScheduleKind.AT:
        return DateTrigger(run_date=parse_at(job.schedule_expr, job.timezone),
                           timezone=tz)

    raise ValueError(f"unknown schedule_kind: {job.schedule_kind}")


def next_fire_at(job: "ScheduledJob", now: datetime) -> datetime | None:
    from src.scheduler.types import ScheduleKind

    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    if job.schedule_kind == ScheduleKind.STARTUP:
        return now + timedelta(seconds=5)

    if job.schedule_kind == ScheduleKind.AT:
        target = parse_at(job.schedule_expr, job.timezone)
        return target if target > now else None

    trigger = build_trigger(job)
    if trigger is None:
        return None
    nxt = trigger.get_next_fire_time(None, now)
    return nxt
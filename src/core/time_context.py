# SPDX-License-Identifier: MIT
"""Real-world time rendered as prompt context.

Pure functions only: `now` is always passed in, never read from the clock, so
the rendered block is reproducible in tests. Nothing here touches config or
storage — the caller supplies the values.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

TIME_OPEN = "<time>"
TIME_CLOSE = "</time>"

LIVING_IN_TIME = """[Living in time]
You know all of the above, and it is real — your sense of time comes from it.
If a long stretch has passed since the user last spoke, let them feel that you
noticed, in your own voice and your own world's words. Acknowledge the time that
passed, not the old topics. Do not say how you know, and never read this block
aloud."""

GROUP_DEDUPE_LINE = (
    "If someone in this conversation has already greeted them back, do not repeat it."
)

WEEKDAYS = (
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
)

_TIME_OF_DAY = (
    (5, "the small hours"),
    (9, "early morning"),
    (12, "morning"),
    (18, "afternoon"),
    (22, "evening"),
    (24, "late at night"),
)

_LEAP_YEAR = 2024


def time_of_day(hour: int) -> str:
    for limit, label in _TIME_OF_DAY:
        if hour < limit:
            return label
    return "late at night"


def parse_birthday(raw) -> tuple[int, int] | None:
    """"MM-DD" to (month, day). Anything unusable becomes None, silently."""
    if not isinstance(raw, str):
        return None
    parts = raw.strip().split("-")
    if len(parts) != 2:
        return None
    try:
        month, day = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    try:
        datetime(_LEAP_YEAR, month, day)
    except ValueError:
        return None
    return month, day


def birthday_in_year(year: int, month: int, day: int) -> date:
    """The date of (month, day) in `year`. Feb 29 falls back to Mar 1 in a
    common year, which is the only place that rule lives."""
    try:
        return date(year, month, day)
    except ValueError:
        return date(year, 3, 1)


def next_birthday_in_days(month: int, day: int, now: datetime) -> int:
    """Days until the next occurrence, 0 when it is today.

    Feb 29 falls back to Mar 1 in a common year, so the span is never negative
    and never lands four years out.
    """
    today = now.date()
    for year in (today.year, today.year + 1):
        candidate = birthday_in_year(year, month, day)
        if candidate >= today:
            return (candidate - today).days
    return 0


def _plural(count: int, unit: str) -> str:
    return f"{count} {unit}" if count == 1 else f"{count} {unit}s"


def relative_age_label(seconds: float) -> str:
    if seconds < 90 * 60:
        return f"{_plural(max(1, int(seconds // 60)), 'minute')} ago"
    if seconds < 24 * 3600:
        return f"{_plural(max(1, int(seconds // 3600)), 'hour')} ago"
    days = int(seconds // 86400)
    if days == 1:
        return "yesterday"
    if days < 14:
        return f"{_plural(days, 'day')} ago"
    if days < 60:
        return f"{_plural(max(1, days // 7), 'week')} ago"
    return f"{_plural(max(1, days // 30), 'month')} ago"


def parse_timestamp(raw) -> datetime | None:
    """Epoch seconds (semantic memory) or ISO text (memory chunks, messages)."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if text.isdigit():
        try:
            return datetime.fromtimestamp(int(text))
        except (OverflowError, OSError, ValueError):
            return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def age_seconds(raw_timestamp, now: datetime) -> float | None:
    """Seconds from `raw_timestamp` to now, or None when unusable or future."""
    parsed = parse_timestamp(raw_timestamp)
    if parsed is None:
        return None
    delta = (now - parsed).total_seconds()
    return delta if delta >= 0 else None


def relative_age_prefix(raw_timestamp, now: datetime) -> str:
    """"(3 days ago) " for a stored timestamp, or "" when unusable."""
    age = age_seconds(raw_timestamp, now)
    if age is None:
        return ""
    return f"({relative_age_label(age)}) "


def _birthday_suffix(month: int, day: int, now: datetime) -> str:
    days = next_birthday_in_days(month, day, now)
    if days == 0:
        return ", which is today"
    if days == 1:
        return ", which is tomorrow"
    if days <= 14:
        return f", which is in {days} days"
    return ""


def build_time_block(
    *,
    now: datetime,
    gap_seconds: float | None = None,
    birthday_raw=None,
    gap_floor_seconds: int = 7200,
    group_mode: bool = False,
) -> str:
    """The <time> facts plus the clause that tells the model what to do with
    them. Fact lines address the user in the third person throughout, because
    a room shares one block between every member."""
    if now is None:
        return ""
    lines = [
        f"It is now {WEEKDAYS[now.weekday()]} {now.strftime('%Y-%m-%d, %H:%M')}"
        f" — {time_of_day(now.hour)}, in the user's local time.",
    ]
    birthday = parse_birthday(birthday_raw)
    if birthday is not None:
        month, day = birthday
        lines.append(
            f"The user's birthday is {month:02d}-{day:02d}"
            f"{_birthday_suffix(month, day, now)}."
        )
    if gap_seconds is not None and gap_seconds >= gap_floor_seconds:
        previous = (now - timedelta(seconds=gap_seconds)).strftime("%Y-%m-%d")
        lines.append(
            f"The user's last message was {relative_age_label(gap_seconds)} "
            f"({previous})."
        )
    clause = LIVING_IN_TIME
    if group_mode:
        clause = f"{clause} {GROUP_DEDUPE_LINE}"
    return f"{TIME_OPEN}\n" + "\n".join(lines) + f"\n{TIME_CLOSE}\n\n{clause}"

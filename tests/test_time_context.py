# SPDX-License-Identifier: MIT
from __future__ import annotations

from datetime import datetime

from src.core.time_context import (
    age_seconds,
    build_time_block,
    next_birthday_in_days,
    parse_birthday,
    parse_timestamp,
    relative_age_label,
    relative_age_prefix,
    time_of_day,
)

NOW = datetime(2026, 9, 26, 23, 41)  # a Saturday, late at night


def _facts(block: str) -> str:
    """The text between <time> and </time> — the fact lines only."""
    return block.split("<time>", 1)[1].split("</time>", 1)[0]


def test_time_of_day_buckets():
    assert time_of_day(0) == "the small hours"
    assert time_of_day(4) == "the small hours"
    assert time_of_day(5) == "early morning"
    assert time_of_day(8) == "early morning"
    assert time_of_day(9) == "morning"
    assert time_of_day(11) == "morning"
    assert time_of_day(12) == "afternoon"
    assert time_of_day(17) == "afternoon"
    assert time_of_day(18) == "evening"
    assert time_of_day(21) == "evening"
    assert time_of_day(22) == "late at night"
    assert time_of_day(23) == "late at night"


def test_relative_age_label_buckets():
    assert relative_age_label(60) == "1 minute ago"
    assert relative_age_label(89 * 60) == "89 minutes ago"
    assert relative_age_label(90 * 60) == "1 hour ago"
    assert relative_age_label(2 * 3600) == "2 hours ago"
    assert relative_age_label(86400) == "yesterday"
    assert relative_age_label(3 * 86400) == "3 days ago"
    assert relative_age_label(13 * 86400) == "13 days ago"
    assert relative_age_label(14 * 86400) == "2 weeks ago"
    assert relative_age_label(59 * 86400) == "8 weeks ago"
    assert relative_age_label(60 * 86400) == "2 months ago"


def test_parse_birthday_accepts_mm_dd_only():
    assert parse_birthday("03-14") == (3, 14)
    assert parse_birthday(" 12-31 ") == (12, 31)
    assert parse_birthday("02-29") == (2, 29)


def test_parse_birthday_rejects_junk():
    for bad in ("garbage", "02-30", "13-01", "00-10", "", "2026-03-14", None, 123):
        assert parse_birthday(bad) is None


def test_next_birthday_in_days_today_and_soon():
    assert next_birthday_in_days(9, 26, NOW) == 0
    assert next_birthday_in_days(9, 27, NOW) == 1
    assert next_birthday_in_days(10, 9, NOW) == 13
    assert next_birthday_in_days(10, 11, NOW) == 15


def test_next_birthday_in_days_never_negative_across_new_year():
    # A birthday already past this year resolves to this year's remaining
    # occurrence, never to a negative span.
    assert next_birthday_in_days(12, 31, datetime(2026, 1, 2, 10, 0)) == 363
    assert next_birthday_in_days(1, 2, datetime(2026, 12, 30, 10, 0)) == 3


def test_next_birthday_in_days_feb29_handling():
    # 2027 is not a leap year, so 02-29 rolls to 03-01 by rule.
    assert next_birthday_in_days(2, 29, datetime(2026, 9, 26, 12, 0)) == 156
    assert next_birthday_in_days(2, 29, datetime(2026, 3, 1, 12, 0)) == 0
    # 2028 is a leap year, so the real 02-29 is used.
    assert next_birthday_in_days(2, 29, datetime(2028, 2, 1, 12, 0)) == 28


def test_parse_timestamp_accepts_epoch_and_iso():
    assert parse_timestamp("1758900000") == datetime.fromtimestamp(1758900000)
    assert parse_timestamp("2026-09-26T23:41:00") == datetime(2026, 9, 26, 23, 41)


def test_parse_timestamp_rejects_junk():
    for bad in (None, "", "nonsense", "-100"):
        assert parse_timestamp(bad) is None


def test_age_seconds_rejects_future_and_junk():
    assert age_seconds("2026-09-25T23:41:00", NOW) == 86400.0
    assert age_seconds("2026-09-27T00:00:00", NOW) is None
    assert age_seconds(None, NOW) is None
    assert age_seconds("nonsense", NOW) is None


def test_relative_age_prefix_is_empty_when_unusable():
    assert relative_age_prefix("2026-09-23T23:41:00", NOW) == "(3 days ago) "
    assert relative_age_prefix(None, NOW) == ""
    assert relative_age_prefix("nonsense", NOW) == ""


def test_build_time_block_baseline():
    block = build_time_block(now=NOW, gap_seconds=None, birthday_raw=None)
    assert "It is now Saturday 2026-09-26, 23:41 — late at night" in block
    assert "[Living in time]" in block
    assert "last message" not in block
    assert "birthday" not in block


def test_build_time_block_gap_floor_is_inclusive():
    below = build_time_block(
        now=NOW, gap_seconds=119 * 60, gap_floor_seconds=120 * 60,
    )
    assert "last message" not in below
    at = build_time_block(
        now=NOW, gap_seconds=120 * 60, gap_floor_seconds=120 * 60,
    )
    assert "The user's last message was 2 hours ago" in at


def test_build_time_block_gap_line_carries_the_previous_date():
    block = build_time_block(
        now=NOW, gap_seconds=3 * 86400, gap_floor_seconds=120 * 60,
    )
    assert "The user's last message was 3 days ago (2026-09-23)." in block


def test_build_time_block_birthday_proximity():
    def line(raw: str) -> str:
        return [
            l for l in _facts(build_time_block(now=NOW, birthday_raw=raw)).splitlines()
            if "birthday" in l
        ][0]

    assert line("09-26") == "The user's birthday is 09-26, which is today."
    assert line("09-27") == "The user's birthday is 09-27, which is tomorrow."
    assert line("09-29") == "The user's birthday is 09-29, which is in 3 days."
    assert line("10-11") == "The user's birthday is 10-11."
    assert line("03-14") == "The user's birthday is 03-14."


def test_build_time_block_drops_unusable_birthday():
    for bad in ("garbage", "02-30", "13-01", None, 123):
        assert "birthday" not in build_time_block(now=NOW, birthday_raw=bad)


def test_build_time_block_group_mode_adds_dedupe_line():
    solo = build_time_block(now=NOW, group_mode=False)
    group = build_time_block(now=NOW, group_mode=True)
    assert "already greeted them back" not in solo
    assert "already greeted them back" in group


def test_fact_lines_never_address_the_user_as_you():
    """Every member of a room reads the same block, so a second-person "you"
    would be read by each of them as being about themselves."""
    for group_mode in (False, True):
        facts = _facts(build_time_block(
            now=NOW,
            gap_seconds=3 * 86400,
            birthday_raw="09-29",
            group_mode=group_mode,
        ))
        lowered = facts.lower()
        assert "you" not in lowered
        assert "your" not in lowered


def test_the_day_itself_gets_a_directive():
    block = build_time_block(now=NOW, birthday_raw="09-26")
    assert "Today is the user's birthday" in block
    assert "wish them a happy birthday" in block


def test_the_directive_is_absent_on_every_other_day():
    for raw in ("09-27", "09-25", "03-14"):
        assert "wish them a happy birthday" not in build_time_block(
            now=NOW, birthday_raw=raw,
        )


def test_the_directive_stays_out_of_the_fact_lines():
    """The facts are shared with every room member and address the user in the
    third person; the directive addresses the character, so it lives in the
    clause instead."""
    facts = _facts(build_time_block(now=NOW, birthday_raw="09-26"))
    assert "wish them a happy birthday" not in facts
    lowered = facts.lower()
    assert "you" not in lowered
    assert "your" not in lowered

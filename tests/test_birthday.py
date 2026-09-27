# SPDX-License-Identifier: MIT
from __future__ import annotations

from datetime import date, datetime

from src.core.birthday import (
    CATCH_UP_DAYS,
    LETTERS,
    BirthdayActions,
    birthday_actions,
    birthday_latest,
    letter_for,
    letters_instruction,
)
from src.core.time_context import birthday_in_year

# The user has been around since well before any date used here.
ARRIVED = date(2026, 1, 1)


def _actions(now, raw, **kw):
    defaults = dict(
        skin_present=False, letter_shown_on=None, letters_year=None,
        arrived_on=ARRIVED,
    )
    defaults.update(kw)
    return birthday_actions(now, raw, **defaults)


def test_the_window_is_a_week():
    assert CATCH_UP_DAYS == 7


def test_on_the_day_everything_fires():
    got = _actions(datetime(2026, 9, 26, 9, 0), "09-26")
    assert got == BirthdayActions(True, True, True, True)


def test_before_the_day_nothing_happens():
    got = _actions(datetime(2026, 9, 20, 9, 0), "09-26")
    assert got == BirthdayActions(False, False, False, False)


def test_still_within_the_window_the_skin_and_letters_catch_up():
    got = _actions(datetime(2026, 9, 30, 9, 0), "09-26")
    assert got == BirthdayActions(
        unlock_skin=True, apply_skin=False, show_letter=False, write_letters=True,
    )


def test_the_last_day_of_the_window_still_pays():
    assert _actions(datetime(2026, 10, 3, 9, 0), "09-26").unlock_skin is True


def test_outside_the_window_nothing_is_paid():
    """One day past the window the year is simply skipped — no half-year-late
    greeting, which is what a user who vanished for months would otherwise get."""
    got = _actions(datetime(2026, 10, 4, 9, 0), "09-26")
    assert got == BirthdayActions(False, False, False, False)
    assert _actions(datetime(2026, 12, 1, 9, 0), "09-26") == BirthdayActions(
        False, False, False, False,
    )


def test_already_unlocked_is_not_unlocked_again():
    got = _actions(datetime(2026, 9, 26, 9, 0), "09-26", skin_present=True)
    assert got.unlock_skin is False
    assert got.apply_skin is True


def test_the_letter_pops_only_once_a_day():
    got = _actions(
        datetime(2026, 9, 26, 9, 0), "09-26", letter_shown_on="2026-09-26",
    )
    assert got.show_letter is False


def test_letters_are_not_rewritten_within_the_same_year():
    got = _actions(datetime(2026, 9, 26, 9, 0), "09-26", letters_year=2026)
    assert got.write_letters is False


def test_letters_are_rewritten_the_next_year():
    got = _actions(
        datetime(2027, 9, 26, 9, 0), "09-26", letters_year=2026,
        arrived_on=date(2025, 1, 1),
    )
    assert got.write_letters is True


def test_unusable_birthday_disables_everything():
    for bad in ("garbage", "02-30", "13-01", None, ""):
        assert _actions(datetime(2026, 9, 26), bad) == BirthdayActions(
            False, False, False, False,
        )


# ---------- arriving after the birthday ----------

def test_a_birthday_that_predates_the_install_is_not_celebrated():
    """Someone whose birthday is 06-03, installing on 06-08: the greeting would
    be for a day that had already happened before they got here."""
    got = _actions(
        datetime(2026, 6, 8, 9, 0), "06-03", arrived_on=date(2026, 6, 8),
    )
    assert got == BirthdayActions(False, False, False, False)


def test_installing_on_the_birthday_itself_still_celebrates():
    got = _actions(
        datetime(2026, 6, 3, 20, 0), "06-03", arrived_on=date(2026, 6, 3),
    )
    assert got == BirthdayActions(True, True, True, True)


def test_an_unknown_arrival_date_never_catches_up():
    """No install record means no evidence the user was here for that birthday,
    and the celebration itself must still work on the day."""
    missed = _actions(
        datetime(2026, 9, 30, 9, 0), "09-26", arrived_on=None,
    )
    assert missed == BirthdayActions(False, False, False, False)
    on_the_day = _actions(
        datetime(2026, 9, 26, 9, 0), "09-26", arrived_on=None,
    )
    assert on_the_day == BirthdayActions(True, True, True, True)


# ---------- the most recent occurrence, not this calendar year's ----------

def test_a_december_birthday_read_in_january_still_pays():
    """The occurrence is the most recent one, so a 12-31 birthday opened on
    01-05 is five days late, not eleven months early."""
    got = _actions(
        datetime(2027, 1, 5, 9, 0), "12-31", arrived_on=date(2025, 1, 1),
    )
    assert got == BirthdayActions(
        unlock_skin=True, apply_skin=False, show_letter=False, write_letters=True,
    )


def test_the_cycle_year_follows_the_most_recent_occurrence():
    assert birthday_latest(datetime(2027, 1, 5, 9), "12-31") == date(2026, 12, 31)
    assert birthday_latest(datetime(2026, 12, 30, 9), "01-02") == date(2026, 1, 2)
    assert birthday_latest(datetime(2026, 9, 26, 9), "09-26") == date(2026, 9, 26)
    assert birthday_latest(datetime(2026, 9, 25, 9), "09-26") == date(2025, 9, 26)
    assert birthday_latest(datetime(2026, 9, 25, 9), "garbage") is None


def test_letters_are_rewritten_for_the_new_cycle_in_january():
    """A 12-31 birthday celebrated on 01-05 belongs to the previous cycle, so
    the year compared against must be the occurrence's, not today's."""
    got = _actions(
        datetime(2027, 1, 5, 9, 0), "12-31", letters_year=2026,
        arrived_on=date(2025, 1, 1),
    )
    assert got.write_letters is False
    fresh = _actions(
        datetime(2027, 1, 5, 9, 0), "12-31", letters_year=2025,
        arrived_on=date(2025, 1, 1),
    )
    assert fresh.write_letters is True


def test_feb29_read_in_a_common_year():
    assert birthday_in_year(2027, 2, 29).isoformat() == "2027-03-01"
    assert birthday_in_year(2028, 2, 29).isoformat() == "2028-02-29"
    got = _actions(
        datetime(2027, 3, 1, 9, 0), "02-29", arrived_on=date(2025, 1, 1),
    )
    assert got.show_letter is True


def test_every_supported_locale_has_a_letter():
    for locale in ("zh-Hans", "zh-Hant", "en", "ja", "de", "fr"):
        body = letter_for(locale)
        assert body.strip()
        assert "FSAR" in body
    assert letter_for(None) == LETTERS["en"]
    assert letter_for("klingon") == LETTERS["en"]


def test_the_instruction_names_the_language_and_forbids_meta():
    text = letters_instruction("zh-Hans")
    assert "Chinese" in text
    assert "system" in text and "prompt" in text

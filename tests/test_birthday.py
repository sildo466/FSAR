# SPDX-License-Identifier: MIT
from __future__ import annotations

from datetime import datetime

from src.core.birthday import (
    LETTERS,
    BirthdayActions,
    birthday_actions,
    letter_for,
    letters_instruction,
)
from src.core.time_context import birthday_in_year


def _actions(now, raw, **kw):
    defaults = dict(skin_present=False, letter_shown_on=None, letters_year=None)
    defaults.update(kw)
    return birthday_actions(now, raw, **defaults)


def test_on_the_day_everything_fires():
    got = _actions(datetime(2026, 9, 26, 9, 0), "09-26")
    assert got == BirthdayActions(True, True, True, True)


def test_after_the_day_unlocks_and_writes_but_neither_applies_nor_pops():
    got = _actions(datetime(2026, 9, 30, 9, 0), "09-26")
    assert got == BirthdayActions(
        unlock_skin=True, apply_skin=False, show_letter=False, write_letters=True,
    )


def test_before_the_day_nothing_happens():
    got = _actions(datetime(2026, 9, 20, 9, 0), "09-26")
    assert got == BirthdayActions(False, False, False, False)


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
    got = _actions(datetime(2027, 9, 26, 9, 0), "09-26", letters_year=2026)
    assert got.write_letters is True


def test_unusable_birthday_disables_everything():
    for bad in ("garbage", "02-30", "13-01", None, ""):
        assert _actions(datetime(2026, 9, 26), bad) == BirthdayActions(
            False, False, False, False,
        )


def test_a_december_birthday_missed_into_january_waits_for_next_year():
    """Known limitation, not an accident: the gift is due from *this calendar
    year's* occurrence. Counting back to the most recent occurrence instead
    would hand a March install the skin six months before a September
    birthday, and avoiding both would need an invented catch-up window."""
    got = _actions(datetime(2027, 1, 5, 9, 0), "12-31")
    assert got == BirthdayActions(False, False, False, False)


def test_a_december_birthday_missed_by_days_in_the_same_year_still_pays():
    got = _actions(datetime(2026, 12, 31, 9, 0), "12-31")
    assert got == BirthdayActions(True, True, True, True)


def test_feb29_read_in_a_common_year():
    assert birthday_in_year(2027, 2, 29).isoformat() == "2027-03-01"
    assert birthday_in_year(2028, 2, 29).isoformat() == "2028-02-29"
    # On 03-01 of a common year the fallback day IS today.
    got = _actions(datetime(2027, 3, 1, 9, 0), "02-29")
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

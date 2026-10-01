# SPDX-License-Identifier: MIT
"""The room's phase machine, as a function of the board and nothing else."""

from __future__ import annotations

from types import SimpleNamespace

from src.server.room_phase import PHASES, decide_phase, is_dispatchable


def _item(status: str, owner: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(status=status, owner_ref=owner)


def test_the_five_phases_are_the_ones_the_gui_knows() -> None:
    assert PHASES == ("chat", "planning", "working", "review", "done")


def test_only_an_owned_todo_is_dispatchable() -> None:
    assert is_dispatchable(_item("todo", "7")) is True
    assert is_dispatchable(_item("todo")) is False
    assert is_dispatchable(_item("doing", "7")) is False
    assert is_dispatchable(_item("done", "7")) is False
    assert is_dispatchable(_item("blocked", "7")) is False


def test_planning_waits_until_every_item_has_an_owner() -> None:
    assert decide_phase("planning", [_item("todo", "7")], in_flight=0) == (
        "working", "all_owned",
    )
    assert decide_phase("planning", [_item("todo")], in_flight=0) is None
    assert decide_phase(
        "planning", [_item("todo", "7"), _item("todo")], in_flight=0,
    ) is None


def test_planning_with_an_empty_board_stays_put() -> None:
    assert decide_phase("planning", [], in_flight=0) is None


def test_working_waits_while_a_turn_is_in_flight() -> None:
    assert decide_phase("working", [_item("doing", "7")], in_flight=1) is None


def test_a_doing_item_holds_the_room_even_when_nobody_remembers_starting_it() -> None:
    """`in_flight` only counts the turns this process opened. After a restart
    it is empty while the board still says `doing` — which is work in progress,
    not 'everything is finished'."""
    assert decide_phase("working", [_item("doing", "7")], in_flight=0) is None


def test_working_stays_while_something_is_still_dispatchable() -> None:
    assert decide_phase(
        "working", [_item("todo", "7"), _item("done", "8")], in_flight=0,
    ) is None


def test_everything_done_goes_to_review() -> None:
    assert decide_phase("working", [_item("done", "7")], in_flight=0) == (
        "review", "all_done",
    )


def test_an_empty_board_goes_to_review_too() -> None:
    assert decide_phase("working", [], in_flight=0) == ("review", "all_done")


def test_a_stuck_board_says_which_kind_of_stuck_it_is() -> None:
    assert decide_phase("working", [_item("blocked", "7")], in_flight=0) == (
        "review", "all_blocked",
    )
    assert decide_phase("working", [_item("todo")], in_flight=0) == (
        "review", "no_owner",
    )
    assert decide_phase(
        "working", [_item("blocked", "7"), _item("done", "8")], in_flight=0,
    ) == ("review", "all_blocked")


def test_an_unowned_item_does_not_hide_a_blocked_one() -> None:
    """Blocked is the more actionable of the two: it names a thing a person
    must decide, where 'no owner' is usually fixed by the next planning round."""
    assert decide_phase(
        "working", [_item("todo"), _item("blocked", "7")], in_flight=0,
    ) == ("review", "all_blocked")


def test_the_other_phases_are_driven_by_the_user_not_by_the_board() -> None:
    for phase in ("chat", "review", "done"):
        assert decide_phase(phase, [_item("todo", "7")], in_flight=0) is None


def test_a_phase_that_is_not_known_is_left_alone() -> None:
    assert decide_phase("nonsense", [_item("todo", "7")], in_flight=0) is None


def test_an_unknown_status_is_not_dispatchable() -> None:
    assert is_dispatchable(_item("finished", "7")) is False

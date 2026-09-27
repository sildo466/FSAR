# SPDX-License-Identifier: MIT
"""Bounded token buckets for the LAN surface."""

from __future__ import annotations

from src.security.rate_budget import RateBudget


def test_allows_up_to_the_burst() -> None:
    budget = RateBudget()
    assert all(
        budget.allow("ip-1", limit=3, per_seconds=60, burst=3) for _ in range(3)
    )


def test_refuses_when_the_burst_is_spent() -> None:
    budget = RateBudget()
    for _ in range(3):
        assert budget.allow("ip-1", limit=3, per_seconds=60, burst=3) is True
    assert budget.allow("ip-1", limit=3, per_seconds=60, burst=3) is False


def test_keys_do_not_share_a_bucket() -> None:
    budget = RateBudget()
    for _ in range(3):
        budget.allow("ip-1", limit=3, per_seconds=60, burst=3)
    assert budget.allow("ip-2", limit=3, per_seconds=60, burst=3) is True


def test_budget_refills_over_time() -> None:
    budget = RateBudget()
    for _ in range(3):
        assert budget.allow(
            "ip-1", limit=3, per_seconds=60, burst=3, now=0.0
        ) is True
    assert budget.allow(
        "ip-1", limit=3, per_seconds=60, burst=3, now=0.0
    ) is False
    # A minute later the bucket is full again.
    assert budget.allow(
        "ip-1", limit=3, per_seconds=60, burst=3, now=60.0
    ) is True


def test_a_rate_of_one_per_second() -> None:
    budget = RateBudget()
    assert budget.allow("m", limit=60, per_seconds=60, burst=1, now=0.0) is True
    assert budget.allow("m", limit=60, per_seconds=60, burst=1, now=0.0) is False
    assert budget.allow("m", limit=60, per_seconds=60, burst=1, now=1.0) is True


def test_the_key_table_stays_bounded() -> None:
    budget = RateBudget(max_keys=16)
    for i in range(1000):
        budget.allow(f"attacker-{i}", limit=5, per_seconds=60, burst=5, now=float(i))
    # 16 real keys plus the overflow bucket, which is created outside the cap —
    # if it counted, it could be evicted the instant the table filled up and
    # "bounded" would quietly become unbounded.
    assert budget.tracked_keys() <= 17


def test_overflow_keys_share_one_bucket() -> None:
    budget = RateBudget(max_keys=2)
    assert budget.allow("a", limit=9, per_seconds=60, burst=2, now=0.0) is True
    assert budget.allow("b", limit=9, per_seconds=60, burst=2, now=0.0) is True
    # a and b filled the table; c and d now share the overflow bucket.
    assert budget.allow("c", limit=9, per_seconds=60, burst=2, now=0.0) is True
    assert budget.allow("d", limit=9, per_seconds=60, burst=2, now=0.0) is True
    assert budget.allow("e", limit=9, per_seconds=60, burst=2, now=0.0) is False


def test_an_established_key_keeps_its_own_bucket_when_the_table_is_full() -> None:
    budget = RateBudget(max_keys=2)
    budget.allow("a", limit=9, per_seconds=60, burst=1, now=0.0)
    budget.allow("b", limit=9, per_seconds=60, burst=1, now=0.0)
    assert budget.allow("a", limit=9, per_seconds=60, burst=1, now=0.0) is False


def test_a_sub_second_window_refills_at_its_own_rate() -> None:
    """A window below a second must not be rounded up to one: 1 per 0.2s is
    five per second, not one."""
    budget = RateBudget()
    assert budget.allow("k", limit=1, per_seconds=0.2, burst=1, now=0.0) is True
    assert budget.allow("k", limit=1, per_seconds=0.2, burst=1, now=0.0) is False
    assert budget.allow("k", limit=1, per_seconds=0.2, burst=1, now=0.25) is True


def test_a_zero_window_does_not_divide_by_zero() -> None:
    budget = RateBudget()
    assert budget.allow("k", limit=1, per_seconds=0, burst=1, now=0.0) is True
    assert budget.allow("k", limit=1, per_seconds=0, burst=1, now=0.0) is False


def test_a_burst_of_zero_still_allows_one() -> None:
    """A budget nobody can use is a bug, not a policy."""
    budget = RateBudget()
    assert budget.allow("ip-1", limit=1, per_seconds=60, burst=0, now=0.0) is True


def test_reset_empties_everything() -> None:
    budget = RateBudget()
    budget.allow("ip-1", limit=1, per_seconds=60, burst=1)
    budget.reset()
    assert budget.tracked_keys() == 0
    assert budget.allow("ip-1", limit=1, per_seconds=60, burst=1) is True

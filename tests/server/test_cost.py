# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def test_compute_cost_one_million_prompt_tokens():
    """Plan spec example: input 0.001 / 1M, output 0.002 / 1M.

    With per-1M rates and 1M prompt + 100k completion tokens:
    (1_000_000 / 1_000_000) * 0.001 + (100_000 / 1_000_000) * 0.002
    = 1.0 * 0.001 + 0.1 * 0.002 = 0.0012.
    """
    from src.server.handlers import usage as usage_mod

    cost = usage_mod.compute_cost(
        prompt_tokens=1_000_000,
        completion_tokens=100_000,
        pricing={"input_per_1m": 0.001, "output_per_1m": 0.002},
    )
    # 1 * 0.001 + 0.1 * 0.002 = 0.001 + 0.0002 = 0.0012
    assert cost == pytest.approx(0.0012)


def test_compute_cost_returns_zero_without_pricing():
    from src.server.handlers import usage as usage_mod

    assert usage_mod.compute_cost(1000, 500, pricing=None) == 0.0
    assert usage_mod.compute_cost(1000, 500, pricing={}) == 0.0


def test_compute_cost_handles_fractional_input():
    from src.server.handlers import usage as usage_mod

    cost = usage_mod.compute_cost(
        prompt_tokens=500,
        completion_tokens=200,
        pricing={"input_per_1m": 0.003, "output_per_1m": 0.015},
    )
    expected = (500 / 1_000_000) * 0.003 + (200 / 1_000_000) * 0.015
    assert cost == pytest.approx(expected)

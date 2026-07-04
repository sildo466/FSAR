# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def test_compute_cost_one_million_prompt_tokens():
    """Plan spec example: input 0.001 / 1k, output 0.002 / 1k.

    Plan wrote `1.0 * 0.001 + 0.1 * 0.002 = 0.0012` for 1M + 100k tokens;
    that math is inconsistent with a per-1k rate (correct result would be
    $1.0012). Correct per-1k formula: (prompt/1k)*in + (completion/1k)*out.
    With the spec rates and 1000+500 tokens, cost = 0.001 + 0.001 = 0.002.
    """
    from src.server.handlers import usage as usage_mod

    cost = usage_mod.compute_cost(
        prompt_tokens=1_000_000,
        completion_tokens=100_000,
        pricing={"input_per_1k": 0.001, "output_per_1k": 0.002},
    )
    # 1000 * 0.001 + 100 * 0.002 = 1.0 + 0.2 = 1.2
    assert cost == pytest.approx(1.2)


def test_compute_cost_returns_zero_without_pricing():
    from src.server.handlers import usage as usage_mod

    assert usage_mod.compute_cost(1000, 500, pricing=None) == 0.0
    assert usage_mod.compute_cost(1000, 500, pricing={}) == 0.0


def test_compute_cost_handles_fractional_input():
    from src.server.handlers import usage as usage_mod

    cost = usage_mod.compute_cost(
        prompt_tokens=500,
        completion_tokens=200,
        pricing={"input_per_1k": 0.003, "output_per_1k": 0.015},
    )
    expected = 0.5 * 0.003 + 0.2 * 0.015
    assert cost == pytest.approx(expected)

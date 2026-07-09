# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import pytest
from src.core.formula_engine import (
    validate_formula,
    evaluate_formula,
    execute_emotion_formulas,
)


def test_validate_basic_arithmetic():
    ok, err = validate_formula("a + b * 2", ["a", "b"])
    assert ok and err is None


def test_validate_rejects_function_call():
    ok, err = validate_formula("eval(1)", [])
    assert not ok
    assert "Function calls" in err or "disallowed" in err


def test_validate_rejects_property_access():
    ok, err = validate_formula("a.__class__", ["a"])
    assert not ok


def test_validate_rejects_empty():
    ok, err = validate_formula("", [])
    assert not ok


def test_validate_rejects_too_long():
    ok, err = validate_formula("a" + " + b" * 200, ["a", "b"])
    assert not ok


def test_evaluate_basic():
    assert evaluate_formula("1 + 2", {}, 0, 100) == 3


def test_evaluate_with_variables():
    assert evaluate_formula("affection + 5", {"affection": 50}, 0, 100) == 55


def test_evaluate_clamps_to_min_max():
    assert evaluate_formula("1000", {}, 0, 100) == 100
    assert evaluate_formula("-1000", {}, 0, 100) == 0


def test_evaluate_division_by_zero_returns_zero():
    assert evaluate_formula("5 / 0", {}, 0, 100) == 0


def test_evaluate_nested_parens():
    assert evaluate_formula("(1 + 2) * (3 + 4)", {}, 0, 100) == 21


def test_execute_emotion_formulas_one_tick():
    metrics = [
        {"key": "energy", "min": 0, "max": 100, "initial": 50},
        {"key": "mood", "min": -100, "max": 100, "initial": 0},
    ]
    formulas = {"energy": "energy - 0.5", "mood": "mood * 0.95"}
    current = {"energy": 80, "mood": 20}
    result = execute_emotion_formulas(metrics, formulas, current)
    assert result["energy"] == 79.5
    assert result["mood"] == pytest.approx(19.0)


def test_execute_emotion_formulas_skips_metrics_without_formula():
    metrics = [
        {"key": "empathy", "min": 0, "max": 100, "initial": 50},
    ]
    formulas: dict[str, str] = {}
    current = {"empathy": 50}
    result = execute_emotion_formulas(metrics, formulas, current)
    assert result == {"empathy": 50}

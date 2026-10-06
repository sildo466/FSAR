# SPDX-License-Identifier: MIT
from __future__ import annotations

from src.server.group_engine import parse_eagerness


def test_plain_json() -> None:
    assert parse_eagerness('{"eagerness": 8, "reason": "I want to speak"}') == (
        8, "I want to speak",
    )


def test_markdown_fenced_json() -> None:
    raw = '```json\n{"eagerness": 7, "reason": "curious"}\n```'
    assert parse_eagerness(raw) == (7, "curious")


def test_json_with_surrounding_prose() -> None:
    raw = 'Sure. {"eagerness": 3, "reason": "maybe"} Hope that helps.'
    assert parse_eagerness(raw) == (3, "maybe")


def test_empty_input_is_zero() -> None:
    assert parse_eagerness("") == (0, "")


def test_garbage_is_zero() -> None:
    assert parse_eagerness("I do not feel like JSON today") == (0, "")


def test_broken_json_is_zero() -> None:
    assert parse_eagerness('{"eagerness": 5, "reason": ') == (0, "")


def test_score_is_clamped_to_range() -> None:
    assert parse_eagerness('{"eagerness": 99, "reason": "x"}')[0] == 10
    assert parse_eagerness('{"eagerness": -5, "reason": "x"}')[0] == 0


def test_non_numeric_score_is_zero() -> None:
    assert parse_eagerness('{"eagerness": "high", "reason": "x"}') == (0, "")


def test_missing_reason_is_empty_string() -> None:
    assert parse_eagerness('{"eagerness": 6}') == (6, "")


def test_reason_is_truncated() -> None:
    long_reason = "y" * 500
    score, reason = parse_eagerness(f'{{"eagerness": 5, "reason": "{long_reason}"}}')
    assert score == 5
    assert len(reason) == 200


def test_extra_keys_are_tolerated() -> None:
    raw = '{"eagerness": 4, "reason": "meh", "confidence": 0.9}'
    assert parse_eagerness(raw) == (4, "meh")


def test_unrelated_json_object_is_zero() -> None:
    assert parse_eagerness('{"result": "ok"}') == (0, "")

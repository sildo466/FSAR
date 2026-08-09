# SPDX-License-Identifier: MIT
"""Safe expression evaluator for emotion formulas.

Modeled on WordBox's formula-engine.ts (300 lines, MIT). Same safety
constraints: only +, -, *, /, numbers, variable references, parens.
Rejects function calls, property access, assignment, comparison ops.
Formula length cap 500 chars. Returns 0 on any error. Clamps to [min, max].
"""
from __future__ import annotations

import re
from typing import Iterable

_MAX_FORMULA_LEN = 500
_ALLOWED_CHARS = re.compile(r"^[a-zA-Z0-9_.+\-*/() \t]+$")
_VAR_NAME = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
_FUNC_CALL = re.compile(r"\b[a-zA-Z_][a-zA-Z0-9_]*\s*\(")


def _tokenize(expr: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    i = 0
    while i < len(expr):
        ch = expr[i]
        if ch in (" ", "\t"):
            i += 1
            continue
        if ch.isdigit() or (ch == "." and i + 1 < len(expr) and expr[i + 1].isdigit()):
            j = i
            while j < len(expr) and (expr[j].isdigit() or expr[j] == "."):
                j += 1
            tokens.append(("number", expr[i:j]))
            i = j
            continue
        if ch.isalpha() or ch == "_":
            j = i
            while j < len(expr) and (expr[j].isalnum() or expr[j] == "_"):
                j += 1
            tokens.append(("variable", expr[i:j]))
            i = j
            continue
        if ch in "+-*/()":
            tokens.append(("op" if ch in "+-*/" else ch, ch))
            i += 1
            continue
        raise ValueError(f"unexpected char {ch!r} at {i}")
    return tokens


class _Parser:
    def __init__(self, tokens: list[tuple[str, str]]):
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> tuple[str, str] | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def consume(self) -> tuple[str, str]:
        if self.pos >= len(self.tokens):
            raise ValueError("unexpected end")
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def parse(self):
        node = self._addsub()
        if self.pos < len(self.tokens):
            raise ValueError(f"trailing token {self.tokens[self.pos]}")
        return node

    def _addsub(self):
        left = self._muldiv()
        while True:
            t = self.peek()
            if t and t[0] == "op" and t[1] in "+-":
                self.consume()
                right = self._muldiv()
                left = ("bin", t[1], left, right)
            else:
                return left

    def _muldiv(self):
        left = self._unary()
        while True:
            t = self.peek()
            if t and t[0] == "op" and t[1] in "*/":
                self.consume()
                right = self._unary()
                left = ("bin", t[1], left, right)
            else:
                return left

    def _unary(self):
        t = self.peek()
        if t and t[0] == "op" and t[1] == "-":
            self.consume()
            return ("neg", self._primary())
        if t and t[0] == "op" and t[1] == "+":
            self.consume()
        return self._primary()

    def _primary(self):
        t = self.consume()
        if t[0] == "number":
            return ("num", float(t[1]))
        if t[0] == "variable":
            return ("var", t[1])
        if t[0] == "(":
            node = self._addsub()
            close = self.consume()
            if close != (")", ")"):
                raise ValueError("missing )")
            return node
        raise ValueError(f"unexpected {t}")


def _eval(node, values: dict[str, float]) -> float:
    kind = node[0]
    if kind == "num":
        return node[1]
    if kind == "var":
        return float(values.get(node[1], 0))
    if kind == "neg":
        return -_eval(node[1], values)
    if kind == "bin":
        op = node[1]
        l = _eval(node[2], values)
        r = _eval(node[3], values)
        if op == "+":
            return l + r
        if op == "-":
            return l - r
        if op == "*":
            return l * r
        if op == "/":
            return 0.0 if r == 0 else l / r
    return 0.0


def validate_formula(
    formula: str, available_vars: Iterable[str]
) -> tuple[bool, str | None]:
    formula = (formula or "").strip()
    if not formula:
        return False, "Formula is empty"
    if len(formula) > _MAX_FORMULA_LEN:
        return False, f"Formula exceeds {_MAX_FORMULA_LEN} characters"
    if not _ALLOWED_CHARS.match(formula):
        return False, "Formula contains disallowed characters"
    var_set = set(available_vars)
    for m in _FUNC_CALL.finditer(formula):
        name = m.group(0).rstrip("(").strip()
        if name not in var_set:
            return False, f"Function calls not allowed: '{name}()'"
    try:
        _Parser(_tokenize(formula)).parse()
        return True, None
    except ValueError as e:
        return False, f"Parse error: {e}"


def evaluate_formula(
    formula: str, values: dict[str, float], lo: float, hi: float
) -> float:
    try:
        node = _Parser(_tokenize(formula)).parse()
        result = _eval(node, values)
    except Exception:
        return max(lo, min(hi, 0))
    if not (float("-inf") < result < float("inf")):
        return max(lo, min(hi, 0))
    return max(lo, min(hi, result))


def execute_emotion_formulas(
    metrics: list[dict], formulas: dict[str, str], current: dict[str, float]
) -> dict[str, float]:
    result = dict(current)
    for m in metrics:
        key = m["key"]
        formula = formulas.get(key)
        if not formula:
            continue
        values = {**current, **result}
        result[key] = evaluate_formula(formula, values, m["min"], m["max"])
    return result

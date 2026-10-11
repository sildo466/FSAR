# SPDX-License-Identifier: MIT
from __future__ import annotations

from src.tools.builtin.process import ProcessTool
from src.tools.builtin.run_command import RunCommandTool


def test_run_command_requires_a_declared_intent():
    schema = RunCommandTool().parameters
    assert "description" in schema["properties"]
    assert schema["properties"]["description"]["type"] == "string"
    assert "description" in schema["required"]


def test_process_takes_an_intent_but_does_not_require_it():
    schema = ProcessTool().parameters
    assert "description" in schema["properties"]
    assert schema["properties"]["description"]["type"] == "string"
    assert "description" not in schema.get("required", [])

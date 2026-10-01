# SPDX-License-Identifier: MIT
"""plan_write exists only where there is a plan board to write to."""

from __future__ import annotations

from types import SimpleNamespace

from src.server import chat_engine as ce


class _Sink:
    def __init__(self):
        self.calls: list[list[dict]] = []
        self.last_written = [{"item_key": "a"}]

    def replace(self, items):
        self.calls.append(items)
        return self.last_written


def test_the_schema_names_the_tool_and_its_owner_field() -> None:
    fn = ce.PLAN_WRITE_SCHEMA["function"]
    assert fn["name"] == "plan_write"
    item = fn["parameters"]["properties"]["items"]["items"]
    assert set(item["required"]) == {"id", "text", "status"}
    assert set(item["properties"]) >= {"id", "text", "status", "owner", "evidence"}
    assert item["properties"]["status"]["enum"] == ["todo", "doing", "blocked", "done"]


def test_no_sink_means_the_tool_is_absent() -> None:
    """A chat-mode turn has no board, so the tool must not be offered."""
    tools = [{"function": {"name": "read_file"}}]
    out = ce._append_plan_tool(tools, None)
    assert [t["function"]["name"] for t in out] == ["read_file"]


def test_a_sink_adds_exactly_one_plan_write() -> None:
    tools = [{"function": {"name": "read_file"}}]
    out = ce._append_plan_tool(tools, _Sink())
    names = [t["function"]["name"] for t in out]
    assert names.count("plan_write") == 1


def test_the_original_tool_list_is_not_mutated() -> None:
    tools = [{"function": {"name": "read_file"}}]
    ce._append_plan_tool(tools, _Sink())
    assert len(tools) == 1


def test_using_the_tool_writes_through_the_sink() -> None:
    sink = _Sink()
    engine = SimpleNamespace(_agent_plan_sink=sink)
    out = ce.ChatEngine._write_plan(
        engine, [{"id": "a", "text": "t", "status": "todo"}],
    )
    assert sink.calls == [[{"id": "a", "text": "t", "status": "todo"}]]
    assert "1" in out


def test_using_the_tool_with_a_bad_payload_says_so() -> None:
    sink = _Sink()
    engine = SimpleNamespace(_agent_plan_sink=sink)
    out = ce.ChatEngine._write_plan(engine, "not a list")
    assert out.startswith("Error")
    assert sink.calls == []


def test_using_the_tool_with_no_sink_says_so() -> None:
    engine = SimpleNamespace(_agent_plan_sink=None)
    out = ce.ChatEngine._write_plan(
        engine, [{"id": "a", "text": "t", "status": "todo"}],
    )
    assert out.startswith("Error")


def test_the_event_payload_comes_from_the_sink() -> None:
    engine = SimpleNamespace(_agent_plan_sink=_Sink())
    assert ce.ChatEngine._agent_plan_items(engine) == [{"item_key": "a"}]


def test_the_event_payload_is_empty_without_a_sink() -> None:
    engine = SimpleNamespace(_agent_plan_sink=None)
    assert ce.ChatEngine._agent_plan_items(engine) == []

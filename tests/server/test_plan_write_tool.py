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


def test_the_offered_schema_names_the_members_that_may_own_an_item() -> None:
    """plan_write sets the owner itself, so the only refs it can legally write
    have to be in front of it — otherwise every item came back unowned."""
    sink = _Sink()
    sink.owners = [("4", "FSAR (zh)"), ("9", "Ori")]
    description = ce._plan_write_schema(sink)["function"]["description"]
    assert '"4" (FSAR (zh))' in description
    assert '"9" (Ori)' in description
    assert "owner" in description
    # The module-level schema is a shared constant, not a per-call template.
    assert '"4"' not in ce.PLAN_WRITE_SCHEMA["function"]["description"]


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
    out = ce.ChatEngine._write_plan(None, sink, [{"id": "a", "text": "t", "status": "todo"}])
    assert sink.calls == [[{"id": "a", "text": "t", "status": "todo"}]]
    assert "1" in out


def test_using_the_tool_with_a_bad_payload_says_so() -> None:
    sink = _Sink()
    out = ce.ChatEngine._write_plan(None, sink, "not a list")
    assert out.startswith("Error")
    assert sink.calls == []


def test_using_the_tool_with_no_sink_says_so() -> None:
    out = ce.ChatEngine._write_plan(None, None, [{"id": "a", "text": "t", "status": "todo"}])
    assert out.startswith("Error")


def test_the_board_event_is_keyed_by_room() -> None:
    """The client keeps the board per room and drops an event that arrives
    without a room id, so an open panel only moved on reopen."""
    sink = _Sink()
    sink.room_id = 3
    sink.last_written = [{"item_key": "a"}]
    event = ce._plan_updated_event(sink)
    assert event["type"] == "room.plan.updated"
    assert event["room_id"] == 3
    assert event["items"] == [{"item_key": "a"}]


def test_the_event_payload_comes_from_the_sink() -> None:
    assert ce.ChatEngine._plan_items(None, _Sink()) == [{"item_key": "a"}]


def test_the_event_payload_is_empty_without_a_sink() -> None:
    assert ce.ChatEngine._plan_items(None, None) == []


def test_the_sink_travels_on_the_run_state_not_on_the_engine() -> None:
    """A room runs two characters at once in one engine: a sink parked on the
    engine would be cleared by whichever turn finished first."""
    from src.core.agent_runtime import AgentRunState

    state = AgentRunState(root_task_id="t", profile=None)
    assert state.plan_sink is None


def test_run_agent_accepts_the_sink_keyword() -> None:
    import inspect

    params = inspect.signature(ce.ChatEngine._run_agent).parameters
    assert "plan_sink" in params
    assert params["plan_sink"].default is None

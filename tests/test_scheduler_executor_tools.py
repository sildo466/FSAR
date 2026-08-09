"""Tool-call loop in IsolatedExecutor — a tool call must not yield empty text."""
import asyncio
import json
from datetime import datetime, timezone

import pytest

from src.scheduler.executor import BLOCKED_TOOLS, IsolatedExecutor
from src.scheduler.types import (
    DeliveryMode, JobKind, ScheduleKind, ScheduledJob,
)


class _Fn:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class _Call:
    def __init__(self, name, arguments="{}", id="call-1"):
        self.id = id
        self.type = "function"
        self.function = _Fn(name, arguments)


class _Msg:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _Resp:
    def __init__(self, message):
        self.choices = [type("C", (), {"message": message})()]


class _Completions:
    def __init__(self, script):
        self._script = list(script)
        self.seen = []

    def create(self, **kwargs):
        self.seen.append(kwargs)
        return self._script.pop(0)


class _Client:
    def __init__(self, script):
        self.chat = type("Chat", (), {"completions": _Completions(script)})()


class _Registry:
    def __init__(self, names=("web_search", "run_command")):
        self._names = names
        self.calls = []

    def get_tools_for_llm(self):
        return [
            {"type": "function", "function": {"name": n, "parameters": {}}}
            for n in self._names
        ]

    async def execute(self, name, **kwargs):
        self.calls.append((name, kwargs))
        return f"{name} result"


def _job(tools_allow="[]", timeout=60):
    now = datetime.now(timezone.utc)
    return ScheduledJob(
        id=1, name="t", description="", enabled=True,
        schedule_kind=ScheduleKind.AT, schedule_expr="2030-01-01T00:00:00",
        timezone="", job_kind=JobKind.AGENT, prompt="ping",
        tools_allow=tools_allow, model_override="", timeout_seconds=timeout,
        delivery_mode=DeliveryMode.SOCIAL, delivery_target="wechat",
        running_at=None, last_run_at=None, last_status=None, last_error="",
        consecutive_errors=0, created_at=now, updated_at=now,
    )


def _executor(script, registry):
    client = _Client(script)
    ex = IsolatedExecutor(
        llm_client_factory=lambda: client,
        primary_model="m",
        tool_registry=registry,
    )
    return ex, client


def test_tool_call_is_executed_and_text_returned():
    """The reported bug: model answers with tool_calls, job stored ''."""
    script = [
        _Resp(_Msg(content=None, tool_calls=[_Call("web_search", '{"q":"x"}')])),
        _Resp(_Msg(content="here is your reminder")),
    ]
    reg = _Registry()
    ex, client = _executor(script, reg)
    out = asyncio.run(ex.run(_job()))

    assert out == "here is your reminder"
    assert reg.calls == [("web_search", {"q": "x"})]
    followup = client.chat.completions.seen[1]["messages"]
    assert followup[-1]["role"] == "tool"
    assert followup[-1]["content"] == "web_search result"


def test_blocked_tools_never_exposed_when_allow_list_empty():
    reg = _Registry()
    ex, client = _executor([_Resp(_Msg(content="done"))], reg)
    asyncio.run(ex.run(_job(tools_allow="[]")))

    exposed = {
        s["function"]["name"] for s in client.chat.completions.seen[0]["tools"]
    }
    assert exposed == {"web_search"}
    assert not exposed & BLOCKED_TOOLS


def test_blocked_tool_call_is_refused_not_executed():
    script = [
        _Resp(_Msg(content=None, tool_calls=[_Call("run_command", '{"command":"rm -rf /"}')])),
        _Resp(_Msg(content="cannot do that")),
    ]
    reg = _Registry()
    ex, client = _executor(script, reg)
    out = asyncio.run(ex.run(_job()))

    assert out == "cannot do that"
    assert reg.calls == []
    assert "not permitted" in client.chat.completions.seen[1]["messages"][-1]["content"]


def test_tool_error_is_fed_back_not_raised():
    class _Boom(_Registry):
        async def execute(self, name, **kwargs):
            raise RuntimeError("upstream 500")

    script = [
        _Resp(_Msg(content=None, tool_calls=[_Call("web_search")])),
        _Resp(_Msg(content="recovered")),
    ]
    ex, client = _executor(script, _Boom())
    assert asyncio.run(ex.run(_job())) == "recovered"
    assert "upstream 500" in client.chat.completions.seen[1]["messages"][-1]["content"]


def test_loop_cap_drops_tools_to_force_prose():
    script = [
        _Resp(_Msg(content=None, tool_calls=[_Call("web_search")])) for _ in range(5)
    ] + [_Resp(_Msg(content="final answer"))]
    ex, client = _executor(script, _Registry())
    assert asyncio.run(ex.run(_job())) == "final answer"
    assert "tools" not in client.chat.completions.seen[-1]

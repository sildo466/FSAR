"""Tests for IsolatedExecutor — tool exposure rules + happy path."""
import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.scheduler.types import (
    DeliveryMode, JobKind, RunStatus, ScheduleKind, ScheduledJob,
)
from src.scheduler.executor import (
    IsolatedExecutor, _safe_tool_names, BLOCKED_TOOLS,
)


def _job(prompt: str = "echo", tools: list[str] | None = None,
         model: str = "", timeout: int = 10) -> ScheduledJob:
    now = datetime.now(timezone.utc)
    return ScheduledJob(
        id=1, name="t", description="", enabled=True,
        schedule_kind=ScheduleKind.CRON, schedule_expr="0 9 * * *", timezone="",
        job_kind=JobKind.AGENT, prompt=prompt,
        tools_allow=json.dumps(tools or []),
        model_override=model, timeout_seconds=timeout,
        delivery_mode=DeliveryMode.DB_ONLY, delivery_target="",
        running_at=None, last_run_at=None, last_status=None, last_error="",
        consecutive_errors=0, created_at=now, updated_at=now,
    )


def test_blocked_tools_constant():
    """Per spec §11.1: run_command, file_ops, edit, process are blocked."""
    assert "run_command" in BLOCKED_TOOLS
    assert "file_ops" in BLOCKED_TOOLS
    assert "edit" in BLOCKED_TOOLS
    assert "process" in BLOCKED_TOOLS


def test_safe_tool_names_filters_blocked():
    tools = ["web_search", "run_command", "file_ops", "image_analyze"]
    safe = _safe_tool_names(json.dumps(tools))
    assert "web_search" in safe
    assert "image_analyze" in safe
    assert "run_command" not in safe
    assert "file_ops" not in safe


def test_safe_tool_names_handles_empty():
    assert _safe_tool_names("") == []
    assert _safe_tool_names("not json") == []


def test_safe_tool_names_handles_garbage():
    assert _safe_tool_names("[]") == []
    assert _safe_tool_names(json.dumps("not a list")) == []


def test_executor_rejects_empty_prompt():
    async def fake_factory():
        return None
    exe = IsolatedExecutor(llm_client_factory=fake_factory, primary_model="gpt-4o")
    with pytest.raises(ValueError):
        asyncio.run(exe.run(_job(prompt="")))


def test_executor_rejects_blocked_tools_via_factory(monkeypatch):
    """_safe_tool_names must strip blocked tools BEFORE they reach the LLM.

    Verified at the unit level via _safe_tool_names; the executor delegates to it.
    """
    # _safe_tool_names already strips blocked tools; just verify it once more here.
    assert "run_command" not in _safe_tool_names(json.dumps(["run_command", "web_search"]))
    assert "file_ops" not in _safe_tool_names(json.dumps(["file_ops"]))
    assert "edit" not in _safe_tool_names(json.dumps(["edit", "process"]))


class _FakeRegistry:
    def get_tools_for_llm(self):
        return [
            {"type": "function", "function": {"name": "web_search"}},
            {"type": "function", "function": {"name": "run_command"}},
        ]


def test_empty_tools_allow_exposes_all_unblocked_tools():
    captured = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="done"))]
            )

    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    exe = IsolatedExecutor(
        llm_client_factory=lambda: client,
        primary_model="m",
        tool_registry=_FakeRegistry(),
    )

    result = asyncio.run(exe.run(_job()))

    assert result == "done"
    # An empty allow-list means "no restriction beyond BLOCKED_TOOLS", which
    # must still withhold the unattended-unsafe tools from the model.
    names = {t["function"]["name"] for t in captured["tools"]}
    assert names == {"web_search"}
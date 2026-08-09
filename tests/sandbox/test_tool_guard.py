import asyncio
from types import SimpleNamespace

from src.sandbox.tool_guard import guard_command, guard_path
from src.sandbox.workspace_gate import PathVerdict


class Gate:
    def __init__(self, verdict):
        self.verdict = verdict

    def validate_path(self, *args, **kwargs):
        return self.verdict

    def check_command(self, *args, **kwargs):
        return self.verdict


def context(verdict, decision="deny"):
    async def request_escape(*args):
        return decision
    return SimpleNamespace(
        workspace_gate=Gate(verdict), active_workspace_id=1,
        session_id="s", conversation_id="c", request_escape=request_escape,
    )


def test_in_tool_hardline_blocks():
    verdict = PathVerdict("deny", "class A", "hardline", "", "root")
    result = asyncio.run(guard_command("rm -rf /", "bash", {"session_ctx": context(verdict)}))
    assert result.startswith("BLOCKED: sandbox hardline")


def test_in_tool_escape_denial_blocks():
    verdict = PathVerdict("confirm_escape", "outside", "outside_workspace", "x", "root")
    result = asyncio.run(guard_path("file_ops", "read", "x", {"session_ctx": context(verdict)}))
    assert result.startswith("Error: sandbox escape denied")


def test_prevalidated_call_skips_duplicate_gate():
    verdict = PathVerdict("deny", "no", "hardline", "", "root")
    assert asyncio.run(guard_command("rm -rf /", "bash", {"session_ctx": context(verdict), "_sandbox_prevalidated": True})) is None

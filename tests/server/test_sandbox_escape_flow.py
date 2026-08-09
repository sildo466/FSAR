import asyncio
from pathlib import Path
from types import SimpleNamespace

from src.memory.workspace import WorkspaceRepo
from src.sandbox.workspace_gate import PathVerdict, SessionAllowCache, WorkspaceGate
from src.server.chat_engine import ChatEngine
from src.tools.builtin.run_command import RunCommandTool
from src.tools.registry import ToolRegistry


class WS:
    def __init__(self):
        self.messages = []

    async def send_json(self, message):
        self.messages.append(message)


class Config:
    def __init__(self):
        self.values = {"security.always_allow_paths": []}

    def get(self, key, default=None):
        return self.values.get(key, default)

    def patch(self, key, value):
        self.values[key] = value

    def save(self):
        pass


class Bridge:
    def __init__(self, decision):
        self.decision = decision

    async def submit(self, request_id, timeout=60):
        return self.decision


def engine(tmp_path: Path, monkeypatch, verdict, decision="deny"):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    item = object.__new__(ChatEngine)
    item.workspace_repo = WorkspaceRepo(tmp_path / "memory.db")
    item.workspace_gate = SimpleNamespace(
        validate_path=lambda *args, **kwargs: verdict,
        check_command=lambda *args, **kwargs: verdict,
        command_verdicts=lambda *args, **kwargs: [verdict],
    )
    item.sandbox_bridge = Bridge(decision)
    item.sandbox_allow_cache = SessionAllowCache()
    item.config = Config()
    return item


def run(item, ws, name="file_ops", args=None):
    return asyncio.run(item._sandbox_tool_call(ws, "call", name, args or {"operation": "read", "path": "x"}, "conv"))


def real_engine(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    item = object.__new__(ChatEngine)
    item.workspace_repo = WorkspaceRepo(tmp_path / "memory.db")
    item.sandbox_allow_cache = SessionAllowCache()
    item.workspace_gate = WorkspaceGate(item.workspace_repo, item.sandbox_allow_cache)
    item.sandbox_bridge = Bridge("deny")
    item.config = Config()
    item.permissions = SimpleNamespace(no_trust_mode=False)
    item.risk_engine = SimpleNamespace(evaluate=lambda tool, args: SimpleNamespace(
        needs_confirm=lambda: False,
        is_denied=lambda: False,
        effective_risk="SAFE",
        reason="",
    ))
    item.registry = ToolRegistry(auto_track=False)
    item.registry.register(RunCommandTool())
    return item


def test_hardline_blocks_without_escape_push(tmp_path: Path, monkeypatch):
    verdict = PathVerdict("deny", "class A", "hardline", "", "root")
    item = engine(tmp_path, monkeypatch, verdict)
    ws = WS()
    result = run(item, ws, "run_command", {"command": "rm -rf /", "shell": "bash"})
    assert result.startswith("BLOCKED: sandbox hardline")
    assert not any(message["type"] == "tool.sandbox.request_escape" for message in ws.messages)


def test_posix_omitted_shell_blocks_bash_hardline_at_chat_boundary(tmp_path: Path, monkeypatch):
    import src.tools.builtin.run_command as run_command

    monkeypatch.setattr(run_command.sys, "platform", "linux")
    item = real_engine(tmp_path, monkeypatch)
    ws = WS()
    args = {"command": "rm -rf /"}

    result = run(item, ws, "run_command", args)

    assert result.startswith("BLOCKED: sandbox hardline")
    assert args["shell"] == "bash"
    assert not any(message["type"] == "tool.sandbox.request_escape" for message in ws.messages)


def test_posix_omitted_shell_reaches_execution_as_bash(tmp_path: Path, monkeypatch):
    import src.server.chat_engine as chat_engine
    import src.tools.builtin.run_command as run_command

    monkeypatch.setattr(run_command.sys, "platform", "linux")
    monkeypatch.setattr(chat_engine, "append_entry", lambda entry: None)
    item = real_engine(tmp_path, monkeypatch)
    checked_shells = []
    real_command_verdicts = item.workspace_gate.command_verdicts

    def command_verdicts(command, **kwargs):
        checked_shells.append(kwargs["shell"])
        return real_command_verdicts(command, **kwargs)

    monkeypatch.setattr(item.workspace_gate, "command_verdicts", command_verdicts)
    executed = []

    class Process:
        returncode = 0

        async def communicate(self):
            return b"ok", b""

    async def create_subprocess_exec(*argv, **kwargs):
        executed.append(argv)
        return Process()

    monkeypatch.setattr(run_command.asyncio, "create_subprocess_exec", create_subprocess_exec)
    result = asyncio.run(item._execute_guarded(
        WS(), "message", "call", "run_command", {"command": "printf hello"}, "conv"
    ))

    assert result == "ok"
    assert checked_shells == ["bash"]
    assert executed == [("bash", "-c", "printf hello")]


def test_allow_once_pushes_and_audits(tmp_path: Path, monkeypatch):
    verdict = PathVerdict("confirm_escape", "outside", "outside_workspace", str(tmp_path / "outside"), "root")
    item = engine(tmp_path, monkeypatch, verdict, "allow_once")
    ws = WS()
    assert run(item, ws) is None
    assert ws.messages[0]["type"] == "tool.sandbox.request_escape"
    assert item.workspace_repo.list_audit(conversation_id="conv")[0]["verdict"] == "escape_once"


def test_allow_session_populates_cache(tmp_path: Path, monkeypatch):
    target = str(tmp_path / "outside")
    verdict = PathVerdict("confirm_escape", "outside", "outside_workspace", target, "root")
    item = engine(tmp_path, monkeypatch, verdict, "allow_session")
    run(item, WS())
    assert item.sandbox_allow_cache.allows("conv", "outside_workspace", target)


def test_allow_always_persists_path(tmp_path: Path, monkeypatch):
    target = str(tmp_path / "outside.txt")
    verdict = PathVerdict("confirm_escape", "outside", "outside_workspace", target, "root")
    item = engine(tmp_path, monkeypatch, verdict, "allow_always")
    run(item, WS())
    assert target in item.config.get("security.always_allow_paths")


def test_denial_is_audited(tmp_path: Path, monkeypatch):
    verdict = PathVerdict("confirm_escape", "outside", "outside_workspace", "x", "root")
    item = engine(tmp_path, monkeypatch, verdict, "deny")
    assert "escape denied" in run(item, WS())
    assert item.workspace_repo.list_audit(conversation_id="conv")[0]["verdict"] == "denied"

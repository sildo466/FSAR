from pathlib import Path
import asyncio

from src.memory.workspace import WorkspaceRepo
from src.server.handlers import sandbox
from src.server.sandbox_bridge import SandboxBridge
from src.utils.fsar_config import FsarConfig


class FakeWS:
    def __init__(self):
        self.messages = []

    async def send_json(self, message):
        self.messages.append(message)


def context(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    config_path = tmp_path / "fsar.yaml"
    config_path.write_text("security: {}\n", encoding="utf-8")
    config = FsarConfig(config_path)
    return {
        "workspace_repo": WorkspaceRepo(tmp_path / "memory.db"),
        "sandbox_bridge": SandboxBridge(),
        "config": config,
    }


def test_workspace_crud_and_binding(tmp_path: Path, monkeypatch):
    ctx = context(tmp_path, monkeypatch)
    ws = FakeWS()
    asyncio.run(sandbox.dispatch(ws, {"type": "workspace.create", "name": "Code", "root_path": str(tmp_path / "code")}, ctx))
    created = ws.messages[-1]["workspace"]
    asyncio.run(sandbox.dispatch(ws, {"type": "workspace.bind", "conversation_id": "c", "workspace_id": created["id"]}, ctx))
    assert ws.messages[-1]["type"] == "workspace.bound"
    assert ctx["workspace_repo"].get_binding("c")[1] == created["id"]


def test_power_template_requires_opt_in(tmp_path: Path, monkeypatch):
    ctx = context(tmp_path, monkeypatch)
    ws = FakeWS()
    asyncio.run(sandbox.dispatch(ws, {"type": "workspace.create", "name": "Home", "template": "user_home"}, ctx))
    assert ws.messages[-1]["type"] == "error"


def test_hardline_and_sensitive_settings(tmp_path: Path, monkeypatch):
    ctx = context(tmp_path, monkeypatch)
    ws = FakeWS()
    asyncio.run(sandbox.dispatch(ws, {"type": "hardline.set_disabled", "classes": ["E"]}, ctx))
    assert ctx["config"].get("security.hardline_disabled_classes") == ["E"]
    asyncio.run(sandbox.dispatch(ws, {"type": "sensitive.add_custom", "pattern": "*/.npmrc"}, ctx))
    assert ctx["config"].get("security.custom_sensitive_paths") == ["*/.npmrc"]


def test_rejects_global_sensitive_glob(tmp_path: Path, monkeypatch):
    ctx = context(tmp_path, monkeypatch)
    ws = FakeWS()
    asyncio.run(sandbox.dispatch(ws, {"type": "sensitive.add_custom", "pattern": "**"}, ctx))
    assert ws.messages[-1]["code"] == "sensitive_pattern"


def test_snapshot_contains_workspace_security_and_sensitive(tmp_path: Path, monkeypatch):
    snap = sandbox.snapshot(context(tmp_path, monkeypatch))
    assert snap["workspace"]["all_workspaces"][0]["name"] == "Sandbox"
    assert len(snap["security"]["hardline_classes"]) == 9
    assert len(snap["sensitive"]["classes"]) == 4

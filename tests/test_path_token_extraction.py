"""Path token extraction tests — garbage tokens must not reach the gate."""

from __future__ import annotations

from pathlib import Path

from src.memory.workspace import WorkspaceRepo
from src.sandbox.workspace_gate import WorkspaceGate, extract_path_tokens


def _gate(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    repo = WorkspaceRepo(tmp_path / "memory.db")
    root = tmp_path / "workspace"
    root.mkdir()
    workspace = repo.create(name="Project", root_path=str(root), blocked_patterns=[])
    return WorkspaceGate(repo), workspace


def test_registry_paths_do_not_yield_fake_drive_tokens():
    command = (
        "powershell -Command \"$p = (Get-ItemProperty "
        "'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\WeChat.exe' "
        "-ErrorAction SilentlyContinue).'(default)'\""
    )
    tokens = extract_path_tokens(command, "powershell")
    assert not any(t.lower().startswith("m:\\") for t in tokens)
    assert not any("hk" in t.lower() for t in tokens)


def test_quoted_paths_with_spaces_are_kept_whole():
    command = "Get-ChildItem 'C:\\Program Files\\Tencent' -Recurse"
    tokens = extract_path_tokens(command, "powershell")
    assert "C:\\Program Files\\Tencent" in tokens
    assert "C:\\Program" not in tokens


def test_truncated_unquoted_paths_do_not_reach_the_gate(tmp_path, monkeypatch):
    gate, ws = _gate(tmp_path, monkeypatch)
    verdicts = gate.command_verdicts("dir C:\\Program Files\\Tencent", workspace_id=ws.id, shell="cmd")
    assert all(v.resolved_path != "C:\\Program" for v in verdicts)


def test_existing_drive_paths_still_surface():
    tokens = extract_path_tokens("dir C:\\Windows\\System32", "cmd")
    assert "C:\\Windows\\System32" in tokens


def test_home_and_env_paths_are_kept():
    tokens = extract_path_tokens(
        r"Test-Path $HOME\Desktop; Test-Path %USERPROFILE%\Desktop; Test-Path $env:LOCALAPPDATA\Programs",
        "powershell",
    )
    assert any("Desktop" in t for t in tokens)
    assert any("Programs" in t for t in tokens)


def test_relative_tokens_still_surface():
    tokens = extract_path_tokens("git status; cd ..\\src", "powershell")
    assert "..\\src" in tokens or any(".." in t for t in tokens)
from pathlib import Path

from src.memory.workspace import WorkspaceRepo
from src.sandbox.workspace_gate import SessionAllowCache, WorkspaceGate, extract_path_tokens


def build(tmp_path: Path, monkeypatch, **kwargs):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    repo = WorkspaceRepo(tmp_path / "memory.db")
    root = tmp_path / "workspace"
    root.mkdir()
    workspace = repo.create(name="Project", root_path=str(root), allowed_paths=kwargs.pop("allowed", ["**"]), blocked_patterns=kwargs.pop("blocked", []))
    return WorkspaceGate(repo, **kwargs), workspace, root


def test_inside_proceeds(tmp_path: Path, monkeypatch):
    gate, ws, root = build(tmp_path, monkeypatch)
    assert gate.validate_path(str(root / "a.txt"), workspace_id=ws.id, operation="read").action == "proceed"


def test_outside_requires_escape(tmp_path: Path, monkeypatch):
    gate, ws, _ = build(tmp_path, monkeypatch)
    verdict = gate.validate_path(str(tmp_path / "outside.txt"), workspace_id=ws.id, operation="read")
    assert verdict.action == "confirm_escape"
    assert verdict.rule_matched == "outside_workspace"


def test_sensitive_inside_requires_escape(tmp_path: Path, monkeypatch):
    gate, ws, root = build(tmp_path, monkeypatch)
    assert gate.validate_path(str(root / ".env"), workspace_id=ws.id, operation="read").is_sensitive


def test_blocked_pattern_denies(tmp_path: Path, monkeypatch):
    gate, ws, root = build(tmp_path, monkeypatch, blocked=["private/**"])
    assert gate.validate_path(str(root / "private/x"), workspace_id=ws.id, operation="read").action == "deny"


def test_allowlist_requires_escape(tmp_path: Path, monkeypatch):
    gate, ws, root = build(tmp_path, monkeypatch, allowed=["src/**"])
    assert gate.validate_path(str(root / "docs/a"), workspace_id=ws.id, operation="read").action == "confirm_escape"


def test_executable_write_denies(tmp_path: Path, monkeypatch):
    gate, ws, root = build(tmp_path, monkeypatch)
    assert gate.validate_path(str(root / "x.exe"), workspace_id=ws.id, operation="write").action == "deny"


def test_session_allow_proceeds(tmp_path: Path, monkeypatch):
    cache = SessionAllowCache()
    gate, ws, _ = build(tmp_path, monkeypatch, session_allow_cache=cache)
    outside = str(tmp_path / "outside")
    cache.allow("s", "outside_workspace", outside)
    assert gate.validate_path(outside, workspace_id=ws.id, operation="read", session_id="s").action == "proceed"


def test_session_allow_does_not_match_prefix_sibling(tmp_path: Path, monkeypatch):
    cache = SessionAllowCache()
    cache.allow("s", "outside_workspace", str(tmp_path / "foo"))
    assert not cache.allows("s", "outside_workspace", str(tmp_path / "foobar"))


def test_command_hardline_and_path_extraction(tmp_path: Path, monkeypatch):
    gate, ws, _ = build(tmp_path, monkeypatch)
    assert gate.check_command("rm -rf /", workspace_id=ws.id, shell="bash").rule_matched == "hardline"
    assert "C:\\Temp\\x.txt" in extract_path_tokens("type C:\\Temp\\x.txt", "cmd")


def test_always_allow_glob_does_not_match_prefix_sibling(tmp_path: Path, monkeypatch):
    allowed = str(tmp_path / "public" / "**")
    gate, ws, _ = build(tmp_path, monkeypatch, always_allow_paths=[allowed])
    assert gate.validate_path(str(tmp_path / "publicity" / "x"), workspace_id=ws.id, operation="read").action == "confirm_escape"
    assert gate.validate_path(str(tmp_path / "public" / "x"), workspace_id=ws.id, operation="read").action == "proceed"


def test_url_is_not_extracted_as_filesystem_path():
    assert extract_path_tokens("curl https://example.com/api", "bash") == []


def test_windows_relative_parent_and_env_are_extracted():
    assert "..\\secret.txt" in extract_path_tokens("type ..\\secret.txt", "cmd")
    assert "$env:USERPROFILE\\.ssh\\id_rsa" in extract_path_tokens("Get-Content $env:USERPROFILE\\.ssh\\id_rsa", "powershell")
    assert ".." in extract_path_tokens("cd ..; dir", "cmd")

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


def test_room_turn_is_not_waved_through_by_the_permanent_allowlist(tmp_path: Path, monkeypatch):
    """A room turn's boundary is its root alone. The allowlist is a convenience
    for the owner's own conversations, not a licence for whoever can reach the
    room — 15 of the 2026-10-10 incident's audit rows read "permanently
    allowed"."""
    gate, ws, _ = build(tmp_path, monkeypatch, always_allow_paths=[str(tmp_path / "**")])
    outside = str(tmp_path / "private" / "fsar.yaml")

    assert gate.validate_path(outside, workspace_id=ws.id, operation="read").action == "proceed"

    room = gate.validate_path(outside, workspace_id=ws.id, operation="read", room_turn=True)
    assert room.action == "confirm_escape"
    assert room.rule_matched == "outside_workspace"
    assert "permanently" not in room.reason


def test_room_turn_inside_the_root_still_proceeds(tmp_path: Path, monkeypatch):
    gate, ws, root = build(tmp_path, monkeypatch, always_allow_paths=[str(tmp_path / "**")])
    assert gate.validate_path(
        str(root / "a.txt"), workspace_id=ws.id, operation="read", room_turn=True,
    ).action == "proceed"


def test_room_command_verdicts_ignore_the_allowlist_too(tmp_path: Path, monkeypatch):
    """The incident's run_command rows — a recursive scan of the owner's home
    directory — were audited as "path is permanently allowed". They come
    through command_verdicts, so the room rule has to reach it as well."""
    gate, ws, _ = build(tmp_path, monkeypatch, always_allow_paths=[str(tmp_path / "**")])
    # command_verdicts skips absolute tokens that do not exist, so the scan
    # target has to be a real directory for the token to be judged at all.
    private = tmp_path / "private"
    private.mkdir()
    command = f'Get-ChildItem -Path "{private}" -Recurse'

    own = gate.command_verdicts(command, workspace_id=ws.id, shell="powershell")
    assert any("permanently" in v.reason for v in own), "the owner's turn still honours it"

    room = gate.command_verdicts(
        command, workspace_id=ws.id, shell="powershell", room_turn=True,
    )
    assert room, "the command's path token must still be judged"
    assert all("permanently" not in v.reason for v in room)

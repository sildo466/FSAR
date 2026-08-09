import sqlite3
from pathlib import Path

import pytest

from src.memory.workspace import WorkspaceRepo


def repo(tmp_path: Path, monkeypatch) -> WorkspaceRepo:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    return WorkspaceRepo(tmp_path / "memory.db", config_dir=tmp_path / "config")


def test_seed_is_idempotent(tmp_path: Path, monkeypatch):
    store = repo(tmp_path, monkeypatch)
    assert store.list()[0].name == "Sandbox"
    assert store.seed_default_if_empty() is None
    assert len(store.list()) == 1


def test_crud_and_default_transaction(tmp_path: Path, monkeypatch):
    store = repo(tmp_path, monkeypatch)
    created = store.create(name="Project", root_path=str(tmp_path / "project"), allowed_paths=["src/**"])
    assert store.update(created.id, name="Project 2").name == "Project 2"
    store.set_default_for_new(created.id)
    assert store.get_default_for_new().id == created.id
    old = next(item for item in store.list() if item.name == "Sandbox")
    assert store.delete(old.id)


def test_only_one_default(tmp_path: Path, monkeypatch):
    store = repo(tmp_path, monkeypatch)
    with sqlite3.connect(store.db_path) as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO workspaces (name, root_path, default_for_new, created_at, updated_at) VALUES ('Other', 'x', 1, 'n', 'n')")


def test_binding_round_trip_and_lazy_audit(tmp_path: Path, monkeypatch):
    store = repo(tmp_path, monkeypatch)
    workspace = store.get_or_create_binding("conv-1")
    assert store.get_binding("conv-1") == ("conv-1", workspace.id)
    assert store.list_audit(conversation_id="conv-1")[0]["verdict"] == "binding_created"


def test_delete_cascades_binding(tmp_path: Path, monkeypatch):
    store = repo(tmp_path, monkeypatch)
    workspace = store.create(name="Temp", root_path=str(tmp_path / "temp"))
    store.bind("conv", workspace.id)
    store.delete(workspace.id)
    assert store.get_binding("conv") is None


def test_default_cannot_be_deleted(tmp_path: Path, monkeypatch):
    store = repo(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        store.delete(store.get_default_for_new().id)


def test_audit_filters(tmp_path: Path, monkeypatch):
    store = repo(tmp_path, monkeypatch)
    ws = store.get_default_for_new()
    store.append_audit(session_id="a", conversation_id="a", workspace_id=ws.id, tool="file_ops", operation="read", target_path="x", command=None, verdict="proceed", reason="ok")
    assert len(store.list_audit(conversation_id="a")) == 1

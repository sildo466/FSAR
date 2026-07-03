# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from pathlib import Path

from src.utils.fsar_config import FsarConfig


def test_load_minimal_yaml(tmp_path: Path):
    (tmp_path / "fsar.yaml").write_text("memory:\n  sqlite_path: data/x.db\n")
    cfg = FsarConfig(tmp_path / "fsar.yaml")
    assert cfg.get("memory.sqlite_path") == "data/x.db"


def test_get_returns_default_when_missing(tmp_path: Path):
    (tmp_path / "fsar.yaml").write_text("memory:\n  sqlite_path: data/x.db\n")
    cfg = FsarConfig(tmp_path / "fsar.yaml")
    assert cfg.get("llm.active", "fallback") == "fallback"


def test_save_writes_atomic_and_creates_backup(tmp_path: Path):
    p = tmp_path / "fsar.yaml"
    p.write_text("memory:\n  sqlite_path: old.db\n")
    cfg = FsarConfig(p)
    cfg.patch("memory.sqlite_path", "new.db")
    cfg.save()
    assert p.read_text().find("new.db") >= 0
    bak = tmp_path / "fsar.yaml.bak"
    assert bak.exists()
    assert bak.read_text().find("old.db") >= 0

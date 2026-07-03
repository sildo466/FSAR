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


def test_get_llm_config_returns_provider_dict(tmp_path: Path):
    (tmp_path / "fsar.yaml").write_text(
        "llm:\n"
        "  providers:\n"
        "    - id: p1\n"
        "      label: P1\n"
        "      provider_family: openai-compatible\n"
        "      base_url: https://api.example.com/v1\n"
        "      api_key: sk-test\n"
        "      model: model-a\n"
        "      pricing: {input_per_1k: 0.001, output_per_1k: 0.002}\n"
        "      enabled: true\n"
    )
    cfg = FsarConfig(tmp_path / "fsar.yaml")
    p = cfg.get_llm_config("p1")
    assert p["model"] == "model-a"
    assert p["api_key"] == "sk-test"
    assert p["pricing"]["input_per_1k"] == 0.001


def test_get_active_provider_returns_active_entry(tmp_path: Path):
    (tmp_path / "fsar.yaml").write_text(
        "llm:\n"
        "  active: p2\n"
        "  providers:\n"
        "    - id: p1\n"
        "      model: model-a\n"
        "    - id: p2\n"
        "      model: model-b\n"
    )
    cfg = FsarConfig(tmp_path / "fsar.yaml")
    assert cfg.get_active_provider()["model"] == "model-b"


def test_get_active_provider_returns_empty_when_no_active(tmp_path: Path):
    (tmp_path / "fsar.yaml").write_text("llm:\n  providers: []\n")
    cfg = FsarConfig(tmp_path / "fsar.yaml")
    assert cfg.get_active_provider() == {}


def test_get_llm_config_expands_env_var_in_api_key(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FSAR_TEST_KEY", "sk-from-env")
    (tmp_path / "fsar.yaml").write_text(
        "llm:\n"
        "  providers:\n"
        "    - id: p1\n"
        "      api_key: '${FSAR_TEST_KEY}'\n"
        "      model: model-a\n"
    )
    cfg = FsarConfig(tmp_path / "fsar.yaml")
    assert cfg.get_llm_config("p1")["api_key"] == "sk-from-env"

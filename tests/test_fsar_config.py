import pytest

from src.utils.fsar_config import FsarConfig


def _empty() -> dict:
    return {"base_url": "", "api_key": "", "model": ""}


def test_vision_model_defaults_to_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("FSAR_CONFIG_PATH", str(tmp_path / "fsar.yaml"))
    cfg = FsarConfig()
    assert cfg.get_vision_model() == _empty()


def test_vision_model_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("FSAR_CONFIG_PATH", str(tmp_path / "fsar.yaml"))
    cfg = FsarConfig()
    cfg.set_vision_model({"base_url": "https://v.example.com", "api_key": "k", "model": "vl-1"})
    cfg.save()
    cfg2 = FsarConfig()
    assert cfg2.get_vision_model() == {
        "base_url": "https://v.example.com",
        "api_key": "k",
        "model": "vl-1",
    }


def test_vision_model_reset(tmp_path, monkeypatch):
    monkeypatch.setenv("FSAR_CONFIG_PATH", str(tmp_path / "fsar.yaml"))
    cfg = FsarConfig()
    cfg.set_vision_model({"base_url": "https://v.example.com", "api_key": "k", "model": "vl-1"})
    cfg.set_vision_model(None)
    assert cfg.get_vision_model() == _empty()


def test_vision_model_expands_env(monkeypatch):
    monkeypatch.setenv("VKEY", "secret")
    cfg = FsarConfig()
    cfg.patch("llm.vision_model", {
        "base_url": "https://v.example.com",
        "api_key": "${VKEY}",
        "model": "vl-1",
    })
    assert cfg.get_vision_model() == {
        "base_url": "https://v.example.com",
        "api_key": "secret",
        "model": "vl-1",
    }


def test_judge_defaults_to_disabled_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("FSAR_CONFIG_PATH", str(tmp_path / "fsar.yaml"))
    cfg = FsarConfig()
    assert cfg.get_judge() == _empty()


def test_judge_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("FSAR_CONFIG_PATH", str(tmp_path / "fsar.yaml"))
    cfg = FsarConfig()
    cfg.set_judge({"base_url": "https://j.example.com", "api_key": "k", "model": "typesafe/jev"})
    cfg.save()

    reloaded = FsarConfig()
    assert reloaded.get_judge() == {
        "base_url": "https://j.example.com",
        "api_key": "k",
        "model": "typesafe/jev",
    }


def test_judge_reset_clears_all_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("FSAR_CONFIG_PATH", str(tmp_path / "fsar.yaml"))
    cfg = FsarConfig()
    cfg.set_judge({"base_url": "https://j", "api_key": "k", "model": "m"})
    cfg.set_judge({})
    assert cfg.get_judge() == _empty()


def test_judge_expands_env(monkeypatch):
    monkeypatch.setenv("JKEY", "secret")
    cfg = FsarConfig()
    cfg.patch("llm.judge", {
        "base_url": "https://j.example.com",
        "api_key": "${JKEY}",
        "model": "typesafe/jev",
    })
    assert cfg.get_judge()["api_key"] == "secret"


def test_injection_budget_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("FSAR_CONFIG_PATH", str(tmp_path / "fsar.yaml"))
    cfg = FsarConfig()
    assert cfg.inject_budget_chars == 2400
    assert cfg.inject_candidate_cap == 40
    assert cfg.inject_score_floor == 0.35
    assert cfg.inject_max_item_chars == 600


def test_injection_budget_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("FSAR_CONFIG_PATH", str(tmp_path / "fsar.yaml"))
    cfg = FsarConfig()
    cfg.patch("memory.inject_budget_chars", 111)
    cfg.patch("memory.inject_candidate_cap", 12)
    cfg.patch("memory.inject_score_floor", 0.5)
    cfg.patch("memory.inject_max_item_chars", 200)
    assert cfg.inject_budget_chars == 111
    assert cfg.inject_candidate_cap == 12
    assert cfg.inject_score_floor == 0.5
    assert cfg.inject_max_item_chars == 200

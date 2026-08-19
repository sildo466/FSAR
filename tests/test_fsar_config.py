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

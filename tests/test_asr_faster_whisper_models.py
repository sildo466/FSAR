# SPDX-License-Identifier: MIT
"""faster-whisper model management tests."""

import sys
from types import SimpleNamespace

import pytest

from src.providers.asr.adapters import faster_whisper_models as models


@pytest.fixture
def cache(monkeypatch, tmp_path):
    path = tmp_path / "huggingface" / "hub"
    path.mkdir(parents=True)
    monkeypatch.setattr(models, "HF_CACHE_DIR", path)
    return path


def create_snapshot(cache, size="base"):
    root = cache / f"models--Systran--faster-whisper-{size}"
    snapshot = root / "snapshots" / "commit123"
    snapshot.mkdir(parents=True)
    (snapshot / "config.json").write_text("{}", encoding="utf-8")
    (root / "refs").mkdir()
    (root / "refs" / "main").write_text("commit123", encoding="utf-8")
    return root, snapshot


def test_model_sizes_and_empty_list(cache):
    assert models.MODEL_SIZES["base"] == 150_000_000
    assert models.list_downloaded() == []
    assert models.is_downloaded("base") is False


def test_list_and_resolve_downloaded_snapshot(cache):
    _root, snapshot = create_snapshot(cache)
    assert models.list_downloaded() == ["base"]
    assert models.resolve_model_path("base") == snapshot


def test_delete_model(cache):
    root, _snapshot = create_snapshot(cache)
    assert models.delete("base") is True
    assert not root.exists()
    assert models.delete("base") is False


def test_disk_full_precheck(cache, monkeypatch):
    monkeypatch.setattr(
        models.shutil,
        "disk_usage",
        lambda path: SimpleNamespace(free=0),
    )
    with pytest.raises(models.ModelDownloadError) as caught:
        models.download("base")
    assert caught.value.code == "disk_full"


def test_download_uses_hf_hub_cache_and_reports_progress(cache, monkeypatch):
    _root, snapshot = create_snapshot(cache)
    calls = []

    def snapshot_download(**kwargs):
        calls.append(kwargs)
        return str(snapshot)

    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        SimpleNamespace(snapshot_download=snapshot_download),
    )
    monkeypatch.setattr(
        models.shutil,
        "disk_usage",
        lambda path: SimpleNamespace(free=10_000_000_000),
    )
    progress = []
    assert models.download("base", progress=lambda done, total: progress.append((done, total))) == str(snapshot)
    assert calls[0]["cache_dir"] == str(cache)
    assert progress[-1] == (models.MODEL_SIZES["base"], models.MODEL_SIZES["base"])


class _JsonResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


def test_resolve_hf_endpoint_uses_env_override(monkeypatch):
    monkeypatch.setenv("HF_ENDPOINT", "https://my-mirror.example.com")
    monkeypatch.setattr(
        models.httpx,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not be called")),
    )
    resolved = models.resolve_hf_endpoint()
    assert resolved.url == "https://my-mirror.example.com"
    assert resolved.source == "override"


def test_resolve_hf_endpoint_country_cn_uses_mirror(monkeypatch, cache):
    monkeypatch.delenv("HF_ENDPOINT", raising=False)
    monkeypatch.setattr(
        models.httpx,
        "get",
        lambda url, timeout=None: _JsonResponse({"country_code": "CN"}),
    )
    resolved = models.resolve_hf_endpoint()
    assert resolved.url == "https://hf-mirror.com"
    assert resolved.source == "mirror"


def test_resolve_hf_endpoint_non_cn_uses_official(monkeypatch, cache):
    monkeypatch.delenv("HF_ENDPOINT", raising=False)
    monkeypatch.setattr(
        models.httpx,
        "get",
        lambda url, timeout=None: _JsonResponse({"country_code": "DE"}),
    )
    resolved = models.resolve_hf_endpoint()
    assert resolved.url == "https://huggingface.co"
    assert resolved.source == "official"


def test_resolve_hf_endpoint_lookup_failure_defaults_to_mirror(monkeypatch, cache):
    monkeypatch.delenv("HF_ENDPOINT", raising=False)

    def _boom(url, timeout=None):
        raise RuntimeError("connect timeout")

    monkeypatch.setattr(models.httpx, "get", _boom)
    resolved = models.resolve_hf_endpoint()
    assert resolved.url == "https://hf-mirror.com"
    assert resolved.source == "mirror"


def test_download_forwards_resolved_endpoint_mirror(cache, monkeypatch):
    _root, snapshot = create_snapshot(cache)
    calls = []

    def snapshot_download(**kwargs):
        calls.append(kwargs)
        return str(snapshot)

    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        SimpleNamespace(snapshot_download=snapshot_download),
    )
    monkeypatch.setattr(
        models.shutil,
        "disk_usage",
        lambda path: SimpleNamespace(free=10_000_000_000),
    )
    monkeypatch.delenv("HF_ENDPOINT", raising=False)
    monkeypatch.setattr(
        models.httpx,
        "get",
        lambda url, timeout=None: _JsonResponse({"country_code": "CN"}),
    )
    models.download("base")
    assert calls[0]["endpoint"] == "https://hf-mirror.com"


def test_download_forwards_resolved_endpoint_official(cache, monkeypatch):
    _root, snapshot = create_snapshot(cache)
    calls = []

    def snapshot_download(**kwargs):
        calls.append(kwargs)
        return str(snapshot)

    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        SimpleNamespace(snapshot_download=snapshot_download),
    )
    monkeypatch.setattr(
        models.shutil,
        "disk_usage",
        lambda path: SimpleNamespace(free=10_000_000_000),
    )
    monkeypatch.delenv("HF_ENDPOINT", raising=False)
    monkeypatch.setattr(
        models.httpx,
        "get",
        lambda url, timeout=None: _JsonResponse({"country_code": "US"}),
    )
    models.download("base")
    assert calls[0]["endpoint"] == "https://huggingface.co"

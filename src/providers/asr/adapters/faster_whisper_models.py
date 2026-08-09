# SPDX-License-Identifier: MIT
"""Explicit faster-whisper model download and lifecycle management."""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx

HF_CACHE_DIR = Path.home() / ".cache" / "huggingface" / "hub"

OFFICIAL_ENDPOINT = "https://huggingface.co"
MIRROR_ENDPOINT = "https://hf-mirror.com"
IPAPI_URL = "https://ipapi.co/json/"
IPAPI_TIMEOUT_SECONDS = 2.5

MODEL_SIZES: dict[str, int] = {
    "tiny": 75_000_000,
    "base": 150_000_000,
    "small": 500_000_000,
    "medium": 1_500_000_000,
    "large-v3": 3_000_000_000,
}


@dataclass(frozen=True)
class ResolvedEndpoint:
    url: str
    source: str


class ModelDownloadError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _model_root(size: str) -> Path:
    return HF_CACHE_DIR / f"models--Systran--faster-whisper-{size}"


def resolve_hf_endpoint() -> ResolvedEndpoint:
    override = os.environ.get("HF_ENDPOINT")
    if override:
        return ResolvedEndpoint(url=override, source="override")
    try:
        response = httpx.get(IPAPI_URL, timeout=IPAPI_TIMEOUT_SECONDS)
        response.raise_for_status()
        country = (response.json() or {}).get("country_code")
    except Exception:
        return ResolvedEndpoint(url=MIRROR_ENDPOINT, source="mirror")
    if isinstance(country, str) and country.upper() == "CN":
        return ResolvedEndpoint(url=MIRROR_ENDPOINT, source="mirror")
    return ResolvedEndpoint(url=OFFICIAL_ENDPOINT, source="official")


def resolve_model_path(size: str) -> Path | None:
    if size not in MODEL_SIZES:
        return None
    root = _model_root(size)
    ref = root / "refs" / "main"
    if ref.is_file():
        commit = ref.read_text(encoding="utf-8").strip()
        candidate = root / "snapshots" / commit
        if (candidate / "config.json").is_file():
            return candidate
    snapshots = root / "snapshots"
    if snapshots.is_dir():
        for candidate in sorted(snapshots.iterdir(), reverse=True):
            if candidate.is_dir() and (candidate / "config.json").is_file():
                return candidate
    return None


def list_downloaded() -> list[str]:
    return [size for size in MODEL_SIZES if resolve_model_path(size) is not None]


def is_downloaded(size: str) -> bool:
    return resolve_model_path(size) is not None


def download(
    size: str,
    *,
    progress: Callable[[int, int], None] | None = None,
    endpoint: ResolvedEndpoint | None = None,
) -> str:
    if size not in MODEL_SIZES:
        raise ModelDownloadError("unknown", f"unknown model size: {size}")
    HF_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(HF_CACHE_DIR).free
    required = MODEL_SIZES[size] * 2
    if free < required:
        raise ModelDownloadError(
            "disk_full", f"need {required} bytes, only {free} bytes available"
        )
    try:
        from huggingface_hub import snapshot_download
    except ImportError as error:
        raise ModelDownloadError(
            "unknown", "huggingface_hub is required to download models"
        ) from error
    resolved = endpoint or resolve_hf_endpoint()
    try:
        path = snapshot_download(
            repo_id=f"Systran/faster-whisper-{size}",
            cache_dir=str(HF_CACHE_DIR),
            endpoint=resolved.url,
        )
    except Exception as error:
        message = str(error)
        lowered = message.lower()
        if "disk" in lowered or "space" in lowered:
            code = "disk_full"
        elif "404" in lowered or "not found" in lowered:
            code = "hf_unavailable"
        elif any(term in lowered for term in ("connection", "timeout", "https")):
            code = "network"
        else:
            code = "unknown"
        raise ModelDownloadError(code, message) from error
    if progress:
        progress(MODEL_SIZES[size], MODEL_SIZES[size])
    return str(path)


def delete(size: str) -> bool:
    if size not in MODEL_SIZES:
        return False
    root = _model_root(size)
    if not root.exists():
        return False
    shutil.rmtree(root)
    return True


def total_disk_usage_bytes() -> int:
    if not HF_CACHE_DIR.exists():
        return 0
    total = 0
    for size in MODEL_SIZES:
        root = _model_root(size)
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file():
                total += path.stat().st_size
    return total


def model_disk_usage_bytes(size: str) -> int:
    if size not in MODEL_SIZES:
        return 0
    root = _model_root(size)
    if not root.exists():
        return 0
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())

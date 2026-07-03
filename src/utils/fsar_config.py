# SPDX-License-Identifier: Apache-2.0
"""Unified FSAR configuration loader and atomic writer."""

from __future__ import annotations

import os
import shutil
import threading
from pathlib import Path
from typing import Any

import yaml

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "fsar.yaml"


class FsarConfig:
    """Read/write the unified fsar.yaml config file with atomic save."""

    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(path) if path else Path(
            os.environ.get("FSAR_CONFIG_PATH", str(DEFAULT_PATH))
        )
        self._lock = threading.RLock()
        self._settings: dict = {}
        self.load()

    def load(self) -> None:
        with self._lock:
            if self._path.exists():
                with self._path.open("r", encoding="utf-8") as f:
                    self._settings = yaml.safe_load(f) or {}
            else:
                self._settings = {}

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            cur: Any = self._settings
            for part in key.split("."):
                if isinstance(cur, dict) and part in cur:
                    cur = cur[part]
                else:
                    return default
            return cur

    def patch(self, key: str, value: Any) -> None:
        with self._lock:
            cur = self._settings
            parts = key.split(".")
            for part in parts[:-1]:
                cur = cur.setdefault(part, {})
            cur[parts[-1]] = value

    def list_providers(self, *, enabled_only: bool = False) -> list[dict]:
        with self._lock:
            providers = list(self._settings.get("llm", {}).get("providers", []))
        if enabled_only:
            providers = [p for p in providers if p.get("enabled")]
        return providers

    def get_llm_config(self, provider_id: str) -> dict:
        for p in self.list_providers():
            if p.get("id") == provider_id:
                return p
        return {}

    def get_active_provider(self) -> dict:
        active_id = self.get("llm.active", "")
        if not active_id:
            return {}
        return self.get_llm_config(active_id)

    def set_active_provider(self, provider_id: str) -> None:
        self.patch("llm.active", provider_id)

    def add_provider(self, provider: dict) -> None:
        providers = self.list_providers()
        providers.append(provider)
        self.patch("llm.providers", providers)

    def update_provider(self, provider: dict) -> None:
        providers = self.list_providers()
        for i, p in enumerate(providers):
            if p.get("id") == provider.get("id"):
                providers[i] = provider
                self.patch("llm.providers", providers)
                return
        raise ValueError(f"provider not found: {provider.get('id')}")

    def remove_provider(self, provider_id: str) -> None:
        providers = [p for p in self.list_providers() if p.get("id") != provider_id]
        self.patch("llm.providers", providers)

    def save(self) -> None:
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(self._path.suffix + ".tmp")
            with tmp.open("w", encoding="utf-8") as f:
                yaml.safe_dump(self._settings, f, allow_unicode=True, sort_keys=False)
                f.flush()
                os.fsync(f.fileno())
            if self._path.exists():
                shutil.copy2(self._path, self._path.with_suffix(self._path.suffix + ".bak"))
            tmp.replace(self._path)

# SPDX-License-Identifier: MIT
"""Unified FSAR configuration loader and atomic writer."""

from __future__ import annotations

import os
import re
import threading
from pathlib import Path
from typing import Any

import yaml

from src.utils.fsar_home import get_fsar_home
from src.skills.atomic import atomic_write_text

DEFAULT_PATH = get_fsar_home() / "config" / "fsar.yaml"
_default_instance: FsarConfig | None = None

_ENV_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _expand_env(value: Any) -> Any:
    if isinstance(value, str):
        return _ENV_RE.sub(lambda m: os.environ.get(m.group(1), m.group(0)), value)
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    return value


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

    @property
    def llm_cache_enabled(self) -> bool:
        return bool(self.get("llm_cache.enabled", True))

    @property
    def llm_cache_db_path(self) -> str:
        default = str(get_fsar_home() / "data" / "llm_cache.db")
        return str(self.get("llm_cache.db_path", default))

    @property
    def llm_cache_retention(self) -> str:
        return str(self.get("llm_cache.retention", "short"))

    @property
    def llm_cache_session_id(self) -> str:
        return str(self.get("llm_cache.session_id", "") or "")

    @property
    def llm_cache_use_responses_api(self) -> bool:
        return bool(self.get("llm_cache.use_responses_api", False))

    @property
    def llm_cache_l1_max_entries(self) -> int:
        return int(self.get("llm_cache.l1_max_entries", 256))

    @property
    def llm_cache_l1_ttl_seconds(self) -> int:
        return int(self.get("llm_cache.l1_ttl_seconds", 300))

    @property
    def llm_cache_l2_ttl_seconds(self) -> int:
        return int(self.get("llm_cache.l2_ttl_seconds", 86400))

    @property
    def llm_cache_skip_vision(self) -> bool:
        return bool(self.get("llm_cache.skip_vision", True))

    @property
    def reflection_intensity(self) -> str:
        return str(self.get("reflection.intensity", "medium"))

    @property
    def reflection_triggers(self) -> dict:
        """GUI-configured reflection triggers. Empty dict when unset."""
        v = self.get("reflection.triggers", {}) or {}
        return v if isinstance(v, dict) else {}

    @property
    def memory_sqlite_path(self) -> str:
        default = str(get_fsar_home() / "data" / "memory.db")
        return str(self.get("memory.sqlite_path", default))

    @property
    def style_locale(self) -> str:
        value = str(self.get("style.locale", "en") or "en")
        if value in {"en", "zh-Hans", "zh-Hant", "ja", "de", "fr"}:
            return value
        return "en"

    @property
    def chat_default_model(self) -> dict[str, Any]:
        value = self.get("chat.default_model", {})
        if isinstance(value, dict) and value.get("kind") in {"model", "integration"}:
            return dict(value)
        if isinstance(value, str) and value.strip():
            provider, separator, model = value.partition(":")
            if separator:
                return {"kind": "model", "provider": provider.strip(), "model": model.strip()}
        active = self.get_active_provider()
        return {
            "kind": "model",
            "provider": str(active.get("id", self.get("llm.active", ""))),
            "model": str(active.get("model", "")),
        }

    @property
    def short_term_window(self) -> int:
        return int(self.get("memory.short_term_window", 50))

    def list_providers(self, *, enabled_only: bool = False) -> list[dict]:
        with self._lock:
            providers = list(self._settings.get("llm", {}).get("providers", []))
        if enabled_only:
            providers = [p for p in providers if p.get("enabled")]
        return providers

    def get_mcp_servers(self) -> list[dict]:
        """Read MCP server configs from `mcp.servers` in fsar.yaml.

        Returns the list as-authored (not env-expanded) — callers that need
        ${VAR} interpolation in `env` blocks should still call os.path.expandvars
        on the result. Returns [] when the key is absent so callers can fall
        back to env var / mcp_servers.yaml.
        """
        with self._lock:
            return list(self._settings.get("mcp", {}).get("servers", []) or [])

    def get_llm_config(self, provider_id: str) -> dict:
        for p in self.list_providers():
            if p.get("id") == provider_id:
                return _expand_env(p)
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
            if self._path.exists():
                atomic_write_text(
                    self._path.with_suffix(self._path.suffix + ".bak"),
                    self._path.read_text(encoding="utf-8"),
                )
            atomic_write_text(
                self._path,
                yaml.safe_dump(self._settings, allow_unicode=True, sort_keys=False),
            )


def get_default_config() -> FsarConfig:
    global _default_instance
    if _default_instance is None:
        _default_instance = FsarConfig()
    return _default_instance

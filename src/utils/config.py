# SPDX-License-Identifier: MIT
"""Deprecated: thin compatibility shim. Use FsarConfig in src/utils/fsar_config.py."""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

from src.utils.fsar_config import FsarConfig, get_default_config
from src.utils.fsar_home import get_fsar_home as _get_fsar_home

__all__ = ["Config", "get_config", "ROOT_DIR", "CONFIG_DIR", "DATA_DIR"]

ROOT_DIR = Path(__file__).resolve().parents[2]
CONFIG_DIR = _get_fsar_home() / "config"
DATA_DIR = _get_fsar_home() / "data"

_old_get_config = None
try:
    from src.utils import config as _legacy  # noqa: F401

    _old_get_config = _legacy._old_get_config  # type: ignore[attr-defined]
except Exception:
    pass

_warned = False


def get_config() -> FsarConfig:  # type: ignore[override]
    """Return the singleton FsarConfig. Warns once on first use."""
    global _warned
    if not _warned:
        warnings.warn(
            "src.utils.config.get_config is deprecated; use src.utils.fsar_config.FsarConfig directly",
            DeprecationWarning,
            stacklevel=2,
        )
        _warned = True
    return get_default_config()


class Config:  # type: ignore[no-redef]
    """Deprecated alias. Inherits FsarConfig."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        warnings.warn("Config is deprecated; use FsarConfig", DeprecationWarning, stacklevel=2)
        self._impl = FsarConfig(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._impl, name)

from __future__ import annotations

import shutil
from pathlib import Path

from src.utils.fsar_home import get_fsar_home
from src.utils.logger import logger

_MARKER = ".migrated"

_CONFIG_FILES = [
    "config/fsar.yaml",
    "config/mcp_servers.yaml",
    "config/permissions.yaml",
]

_DATA_ITEMS = [
    "data/memory.db",
    "data/llm_cache.db",
    "data/.llm_session_id",
    "data/avatars",
    "data/chroma",
    "data/logs",
]


def _copy_if_absent(src: Path, dst: Path) -> None:
    if dst.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dst)
        logger.info(f"migrate: copied dir {src} -> {dst}")
    else:
        shutil.copy2(src, dst)
        logger.info(f"migrate: copied {src} -> {dst}")


def run_migration(project_root: Path) -> None:
    home = get_fsar_home()
    marker = home / _MARKER
    if marker.exists():
        return

    logger.info(f"migrate: first run detected, migrating user data to {home}")

    for rel in _CONFIG_FILES:
        src = project_root / rel
        dst = home / rel
        if src.exists():
            _copy_if_absent(src, dst)

    for rel in _DATA_ITEMS:
        src = project_root / rel
        dst = home / rel
        if src.exists():
            _copy_if_absent(src, dst)

    home.mkdir(parents=True, exist_ok=True)
    marker.touch()
    logger.info("migrate: done")
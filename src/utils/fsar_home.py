from __future__ import annotations

import os
from pathlib import Path


def get_fsar_home() -> Path:
    override = os.environ.get("FSAR_HOME", "").strip()
    if override:
        return Path(override)
    return Path.home() / ".fsar"

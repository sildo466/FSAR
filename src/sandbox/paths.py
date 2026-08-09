"""Path normalization and workspace containment helpers."""

from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path

_IGNORED = {"\u200b", "\u200c", "\u200d", "\ufeff", "\u2060"}
_POWERSHELL_ENV = re.compile(r"(?i)\$env:([A-Z_][A-Z0-9_]*)")


def normalize_path(raw_path: str) -> str:
    value = unicodedata.normalize("NFKC", str(raw_path))
    value = "".join(ch for ch in value if ch not in _IGNORED).strip()
    if value.startswith("@"):
        value = value[1:].lstrip()
    value = _POWERSHELL_ENV.sub(lambda match: os.environ.get(match.group(1), match.group(0)), value)
    value = os.path.expandvars(value)
    if value == "$HOME" or value.startswith("$HOME/") or value.startswith("$HOME\\"):
        value = str(Path.home()) + value[5:]
    return value


def safe_resolve(raw_path: str, *, base: Path | None = None) -> Path:
    value = normalize_path(raw_path)
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (base or Path.cwd()) / path
    return path.resolve(strict=False)


def is_inside(path: Path, root: Path) -> bool:
    resolved_path = path.resolve(strict=False)
    resolved_root = root.resolve(strict=False)
    if os.name == "nt":
        path_text = os.path.normcase(str(resolved_path))
        root_text = os.path.normcase(str(resolved_root))
        try:
            return os.path.commonpath([path_text, root_text]) == root_text
        except ValueError:
            return False
    try:
        resolved_path.relative_to(resolved_root)
        return True
    except ValueError:
        return False

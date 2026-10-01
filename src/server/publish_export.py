# SPDX-License-Identifier: MIT
"""The snapshot that leaves the project.

An allowlist, never a deny list. The things that must not leave are ordinary
text — `.env`, `.npmrc`, a token in a config file — and there is no end to
the list of them, so the only workable rule is to name what goes.

No history goes with it. A clone carries every secret ever committed and
later removed, so the snapshot is a package of files and nothing else.
"""

from __future__ import annotations

import fnmatch
import hashlib
import os
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path

from src.utils.fsar_home import get_fsar_home

MAX_FILE_BYTES = 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
_BINARY_SNIFF_BYTES = 8192
_SKIP_DIRS = frozenset({
    "__pycache__", "node_modules", "venv", ".venv", "dist", "build",
})


class ExportError(RuntimeError):
    pass


@dataclass
class ExportResult:
    path: Path
    path_count: int
    byte_count: int
    digest: str


def publish_dir(room_id: int) -> Path:
    return get_fsar_home() / "publishes" / f"room-{int(room_id)}"


def package_for(room_id: int, digest: str) -> Path:
    return publish_dir(room_id) / f"publish-{digest[:16]}.tar.gz"


def matches_allowlist(relpath: str, allowlist: list[str]) -> bool:
    path = str(relpath).replace("\\", "/")
    return any(
        fnmatch.fnmatch(path, str(pattern).replace("\\", "/"))
        for pattern in allowlist
    )


def _hidden(rel: Path) -> bool:
    return any(part.startswith(".") for part in rel.parts)


def _looks_like_text(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return b"\0" not in handle.read(_BINARY_SNIFF_BYTES)
    except OSError:
        return False


def collect(project_root: str | Path, allowlist: list[str]) -> list[Path]:
    """Relative paths that may leave, sorted, or nothing at all.

    An empty allowlist publishes nothing: a default that lets everything
    through would make the allowlist decorative.
    """
    if not allowlist:
        raise ExportError("no allowlist configured")
    root = Path(project_root).resolve()
    taken: list[Path] = []
    total = 0
    for dirpath, dirnames, filenames in os.walk(root):
        here = Path(dirpath)
        dirnames[:] = sorted(
            name for name in dirnames
            if not name.startswith(".")
            and name not in _SKIP_DIRS
            and not (here / name).is_symlink()
        )
        for name in sorted(filenames):
            path = here / name
            if path.is_symlink() or not path.is_file():
                continue
            rel = path.relative_to(root)
            if _hidden(rel):
                continue
            if not matches_allowlist(str(rel).replace("\\", "/"), allowlist):
                continue
            if os.access(path, os.X_OK) and os.name == "posix":
                continue
            size = path.stat().st_size
            if size > MAX_FILE_BYTES:
                raise ExportError(
                    f"{rel} is larger than the {MAX_FILE_BYTES} byte limit"
                )
            if not _looks_like_text(path):
                continue
            total += size
            if total > MAX_TOTAL_BYTES:
                raise ExportError("the snapshot is larger than the total limit")
            taken.append(rel)
    return taken


def build_export(
    project_root: str | Path, allowlist: list[str], room_id: int,
) -> ExportResult:
    """Package the allowlisted paths. No `.git`, so no history."""
    root = Path(project_root).resolve()
    rels = collect(root, allowlist)
    dest = publish_dir(room_id)
    dest.mkdir(parents=True, exist_ok=True)
    handle, scratch = tempfile.mkstemp(dir=dest, suffix=".part")
    os.close(handle)
    try:
        with tarfile.open(scratch, "w:gz") as tar:
            for rel in rels:
                tar.add(root / rel, arcname=str(rel).replace("\\", "/"))
        digest = hashlib.sha256(Path(scratch).read_bytes()).hexdigest()
        final = package_for(room_id, digest)
        os.replace(scratch, final)
    except Exception:
        Path(scratch).unlink(missing_ok=True)
        raise
    return ExportResult(
        path=final, path_count=len(rels),
        byte_count=final.stat().st_size, digest=digest,
    )

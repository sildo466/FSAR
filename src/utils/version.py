# SPDX-License-Identifier: MIT
"""Version identity derived from the git tag at HEAD.

The tag is the single source of truth for the running build; pyproject.toml is
only a fallback for packaged checkouts that have no .git directory.
"""

from __future__ import annotations

import re
import subprocess
import tomllib
from pathlib import Path

_DESCRIBE_SUFFIX = re.compile(r"-\d+-g[0-9a-f]+$")
_PRERELEASE = re.compile(r"^(?P<base>.+?)-(?P<kind>alpha|beta|rc)(?P<num>\d*)$", re.I)
_DIRTY_SUFFIX = "-dirty"
_REPO_ROOT = Path(__file__).resolve().parents[2]


def base_tag(tag: str) -> str:
    """Strip the `git describe` commit/dirty decoration from a tag.

    Dirty comes off first: a tree that is both ahead of the tag and modified
    describes as `v0.6.0-beta1-1-gca206f5-dirty`, and the commit-suffix pattern
    is anchored at the end so it would not match there.
    """
    stripped = tag.strip()
    if stripped.endswith(_DIRTY_SUFFIX):
        stripped = stripped[: -len(_DIRTY_SUFFIX)]
    return _DESCRIBE_SUFFIX.sub("", stripped)


def parse_tag(tag: str) -> tuple[tuple[int, ...], tuple[str, int] | None] | None:
    """Numeric components plus an optional prerelease marker.

    Returns None when the tag carries no numeric version, so callers report
    "not comparable" instead of inventing an ordering.
    """
    raw = base_tag(tag)
    if raw[:1] in ("v", "V"):
        raw = raw[1:]
    prerelease = None
    match = _PRERELEASE.match(raw)
    if match:
        raw = match.group("base")
        prerelease = (match.group("kind").lower(), int(match.group("num") or 0))
    if not raw:
        return None
    numbers: list[int] = []
    for part in raw.split("."):
        if not part.isdigit():
            return None
        numbers.append(int(part))
    return tuple(numbers), prerelease


def compare_tags(a: str, b: str) -> int | None:
    """-1 when a < b, 0 when equal, 1 when a > b. None when either is unparseable."""
    left, right = parse_tag(a), parse_tag(b)
    if left is None or right is None:
        return None
    left_nums, left_pre = left
    right_nums, right_pre = right
    width = max(len(left_nums), len(right_nums))
    padded_left = left_nums + (0,) * (width - len(left_nums))
    padded_right = right_nums + (0,) * (width - len(right_nums))
    if padded_left != padded_right:
        return -1 if padded_left < padded_right else 1
    if left_pre is None and right_pre is None:
        return 0
    if left_pre is None:
        return 1
    if right_pre is None:
        return -1
    if left_pre == right_pre:
        return 0
    return -1 if left_pre < right_pre else 1


def channel_of(tag: str) -> str:
    """`beta` for any prerelease tag, `stable` otherwise."""
    parsed = parse_tag(tag)
    return "beta" if parsed and parsed[1] is not None else "stable"


def describe_tag(repo: Path) -> str | None:
    """`git describe --tags --always --dirty` in repo, or None when unavailable."""
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--always", "--dirty"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def pyproject_version(repo: Path) -> str | None:
    """`project.version` from pyproject.toml, normalised to a `v`-prefixed tag."""
    path = repo / "pyproject.toml"
    if not path.is_file():
        return None
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return None
    value = (data.get("project") or {}).get("version")
    return f"v{value}" if isinstance(value, str) and value else None


def app_version(repo: Path | None = None) -> dict:
    """Version payload for the WS snapshot."""
    root = repo or _REPO_ROOT
    described = describe_tag(root)
    if described is not None:
        tag, source = described, "git"
    else:
        tag, source = pyproject_version(root) or "unknown", "pyproject"
    base = base_tag(tag)
    return {
        "tag": tag,
        "base": base,
        "channel": channel_of(tag),
        "exact": parse_tag(tag) is not None and base == tag,
        "source": source,
    }

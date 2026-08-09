from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from src.skills.safe_marker import MarkerVerification, SafeMarker
from src.utils.fsar_home import get_fsar_home


_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def validate_subject_name(name: str) -> str:
    if not _SAFE_NAME.fullmatch(name) or name in {".", ".."}:
        raise ValueError("invalid subject name")
    return name


def skill_review_enabled(config: Any) -> bool:
    return bool(config.get("security.skills.review_required", True)) and bool(
        config.get("security.skills.llm_review.enabled", False)
    )


def mcp_review_enabled(config: Any) -> bool:
    return bool(config.get("security.mcp.review_required", True))


def mcp_config_bytes(server_config: dict[str, Any]) -> bytes:
    protected = {
        "name": server_config.get("name"),
        "transport": server_config.get("transport") or "stdio",
        "command": server_config.get("command"),
        "args": server_config.get("args") or [],
        "env": server_config.get("env") or {},
        "cwd": server_config.get("cwd"),
        "url": server_config.get("url"),
        "headers": server_config.get("headers") or {},
    }
    return json.dumps(protected, sort_keys=True, separators=(",", ":")).encode("utf-8")


def gate_skill(
    name: str,
    config: Any,
    *,
    skills_root: Path | None = None,
    marker: SafeMarker | None = None,
) -> MarkerVerification:
    validate_subject_name(name)
    if not skill_review_enabled(config):
        return MarkerVerification(True)
    root = skills_root or get_fsar_home() / "skills"
    return (marker or SafeMarker()).verify(root / name, f"skill:{name}")


def gate_skill_read_path(
    path: Path,
    config: Any,
    *,
    skills_root: Path | None = None,
    marker: SafeMarker | None = None,
) -> MarkerVerification:
    if not skill_review_enabled(config):
        return MarkerVerification(True)
    root = (skills_root or get_fsar_home() / "skills").resolve()
    resolved = path.expanduser().resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError:
        return MarkerVerification(True)
    if not relative.parts:
        return MarkerVerification(False, "skill_root")
    name = relative.parts[0]
    return gate_skill(name, config, skills_root=root, marker=marker)


def gate_mcp(
    server_config: dict[str, Any],
    config: Any,
    *,
    servers_root: Path | None = None,
    marker: SafeMarker | None = None,
) -> MarkerVerification:
    name = validate_subject_name(str(server_config.get("name") or ""))
    if not mcp_review_enabled(config):
        return MarkerVerification(True)
    root = servers_root or get_fsar_home() / "mcp_servers"
    return (marker or SafeMarker()).verify(
        root / name,
        f"mcp:{name}",
        supplemental=mcp_config_bytes(server_config),
    )

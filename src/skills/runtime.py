from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


DEFAULT_ENV_ALLOW = ["PATH", "HOME", "LANG", "TMPDIR", "SYSTEMROOT", "USERPROFILE"]
DEFAULT_STRIP_MARKERS = ["API_KEY", "TOKEN", "SECRET", "AUTH"]


def build_subprocess_env(
    config: Any,
    *,
    source: Mapping[str, str] | None = None,
    extra: Mapping[str, str] | None = None,
) -> dict[str, str]:
    parent = dict(source or os.environ)
    enabled = bool(config.get("security.skills.subprocess_env.enabled", True))
    if enabled:
        allowed = config.get("security.skills.subprocess_env.allow", DEFAULT_ENV_ALLOW)
        allowed_names = {str(item).upper() for item in allowed if isinstance(item, str)}
        environment = {
            name: value for name, value in parent.items() if name.upper() in allowed_names
        }
        strip_markers = config.get(
            "security.skills.subprocess_env.strip_prefixes", DEFAULT_STRIP_MARKERS
        )
        markers = [str(item).upper() for item in strip_markers if isinstance(item, str)]
        for name in list(environment):
            normalized = name.upper()
            if normalized.endswith("_API_KEY") or any(marker in normalized for marker in markers):
                environment.pop(name, None)
    else:
        environment = parent
    environment.update(extra or {})
    return environment


@dataclass(frozen=True)
class SkillProcessResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


async def run_python_skill(
    entrypoint: Path,
    args: dict[str, Any],
    config: Any,
    *,
    timeout: int = 30,
) -> SkillProcessResult:
    serialized = json.dumps(args, ensure_ascii=False)
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        str(entrypoint),
        serialized,
        cwd=str(entrypoint.parent),
        env=build_subprocess_env(config, extra={"FSAR_SKILL_ARGS": serialized}),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=max(1, min(int(timeout), 120))
        )
    except asyncio.TimeoutError:
        process.kill()
        stdout, stderr = await process.communicate()
        return SkillProcessResult(
            process.returncode or -1,
            stdout.decode("utf-8", errors="replace").strip(),
            stderr.decode("utf-8", errors="replace").strip(),
            True,
        )
    return SkillProcessResult(
        process.returncode or 0,
        stdout.decode("utf-8", errors="replace").strip(),
        stderr.decode("utf-8", errors="replace").strip(),
    )

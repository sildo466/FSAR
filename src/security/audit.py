"""FSAR 审计日志 — append-only JSON lines，每条工具决策一行。

注意: 失败也不抛（审计故障不能影响主路径）。
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.utils.config import DATA_DIR


@dataclass
class AuditEntry:
    ts: str
    session: str
    tool: str
    args: dict
    risk: str
    verdict: str          # proceed | confirm | deny
    user_response: str    # "" (auto) | "y" | "n" | "all" | "never"
    outcome: str          # success | denied | cancelled | error
    error: Optional[str] = None
    duration_ms: int = 0


def _audit_path() -> Path:
    d = DATA_DIR / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d / "audit.log"


def append_entry(entry: AuditEntry) -> None:
    try:
        line = json.dumps(asdict(entry), ensure_ascii=False)
        with open(_audit_path(), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception as e:
        # 审计永不抛错（仅 stderr 提示）
        import sys
        print(f"[audit] failed to write: {e}", file=sys.stderr)


def make_entry(*, session: str, tool: str, args: dict, risk: str,
               verdict: str, user_response: str, outcome: str,
               error: Optional[str] = None, duration_ms: int = 0) -> AuditEntry:
    return AuditEntry(
        ts=datetime.now().isoformat(timespec="seconds"),
        session=session,
        tool=tool,
        args=args,
        risk=risk,
        verdict=verdict,
        user_response=user_response,
        outcome=outcome,
        error=error,
        duration_ms=duration_ms,
    )


def tail(n: int = 20) -> list[dict]:
    """最近 n 条审计记录（最新在最后）。"""
    p = _audit_path()
    if not p.exists():
        return []
    try:
        with open(p, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return []
    return [json.loads(line) for line in lines[-n:] if line.strip()]

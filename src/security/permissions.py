"""FSAR 权限加载/持久化 — 解析 config/permissions.yaml 到可查询的 PermissionState。

设计:
- 启动时 load 一次到内存（PermissionState），运行期可 mutate
- mutate 立刻写回 yaml（trust/deny 更改要持久化）
- 纯数据 dataclass，不执行任何工具
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from src.utils.config import CONFIG_DIR
from src.utils.logger import logger


# 默认 yaml（首次启动或文件丢失时使用）
DEFAULT_PERMISSIONS = {
    "mode": "normal",  # strict | normal | trust
    "tools": {
        "run_command": {
            "risk": "HIGH",
            "mode": "ask",
            "blocked_patterns": [
                "rm -rf /",
                "del /s /q C:\\*",
                "format ",
                "rd /s /q C:\\",
            ],
        },
        "file_ops": {
            "risk": "MEDIUM",
            "operations": {
                "read": "trust",
                "write": "trust",
                "list": "trust",
                "move": "ask",
                "delete": "ask",
                "mkdir": "trust",
            },
        },
        "edit": {"risk": "MEDIUM", "mode": "ask"},
        "process": {"risk": "HIGH", "mode": "ask"},
        "web_search": {"risk": "SAFE", "mode": "trust"},
        "web_fetch": {"risk": "SAFE", "mode": "trust"},
        "app_control": {"risk": "LOW", "mode": "ask"},
        "image_analyze": {"risk": "LOW", "mode": "trust"},
        "pdf_analyze": {"risk": "LOW", "mode": "trust"},
    },
    "path_rules": [
        {"match": r"C:\\Windows.*", "action": "deny"},
        {"match": r"C:\\Program Files.*", "action": "deny"},
        {"match": r"C:\\$", "action": "deny", "operations": ["delete", "move"]},
        {"match": r"C:\\$", "action": "deny", "operations": ["write"]},
    ],
}


@dataclass
class PathRule:
    pattern: str
    action: str  # "deny" | "ask"
    operations: list[str] = field(default_factory=list)  # empty = any
    compiled: re.Pattern = field(init=False, repr=False)

    def __post_init__(self):
        self.compiled = re.compile(self.pattern, re.IGNORECASE)

    def matches(self, path: str, operation: Optional[str] = None) -> bool:
        if not self.compiled.match(path):
            return False
        if not self.operations:
            return True
        return operation in self.operations if operation else True


@dataclass
class PermissionState:
    """permissions.yaml 在内存中的表示 — 可修改、可写回。"""

    mode: str = "normal"  # strict | normal | trust
    tools: dict = field(default_factory=dict)  # tool_name -> { risk, mode, operations?, blocked_patterns? }
    path_rules: list[PathRule] = field(default_factory=list)
    # 会话级临时 trust（不写回 yaml，进程结束清空）
    session_trust: set[str] = field(default_factory=set)
    # 会话级临时 deny（不写回 yaml）
    session_deny: set[str] = field(default_factory=set)
    # 会话级 server trust（per-server 而非 per-tool，让一个 MCP server 内的全部 tool 一次性放行）
    server_trust: set[str] = field(default_factory=set)
    no_trust_mode: bool = False

    def tool_mode(
        self,
        tool_name: str,
        operation: Optional[str] = None,
        server_name: Optional[str] = None,
    ) -> Optional[str]:
        """查某个 tool (或 tool.operation) 的 mode：trust | ask | deny | None。

        优先级: session_deny > session_trust > server_trust > yaml
        返回 None 表示工具既不在 yaml 里、也没有任何 session 级放行——交给
        RiskEngine 用 effective_risk + session.mode 阈值决定（而不是默认 ask）。
        这样 MCP 这类动态注册的工具不会被无条件地卡在 confirm 分支。
        """
        if tool_name in self.session_deny:
            return "deny"
        if tool_name in self.session_trust:
            return "trust"
        if server_name and server_name in self.server_trust:
            return "trust"

        tool_cfg = self.tools.get(tool_name)
        if not tool_cfg:
            return None
        # 优先: operations.{op}.mode 否则 operations.{op} 自身就是 mode
        if operation and "operations" in tool_cfg and operation in tool_cfg["operations"]:
            op_val = tool_cfg["operations"][operation]
            if isinstance(op_val, dict):
                return op_val.get("mode", "ask")
            return str(op_val)  # 简短写法: "trust"/"ask"/"deny"

        return tool_cfg.get("mode", "ask")

    def tool_risk(self, tool_name: str) -> str:
        """tool 声明的 risk 等级（用于审计/UI 展示）。"""
        tool_cfg = self.tools.get(tool_name, {})
        return tool_cfg.get("risk", "MEDIUM")

    def blocked_patterns(self, tool_name: str) -> list[str]:
        """tool 配置里的 blocked_patterns。"""
        tool_cfg = self.tools.get(tool_name, {})
        return list(tool_cfg.get("blocked_patterns", []))

    def set_session_trust(self, tool_name: str) -> None:
        if self.no_trust_mode:
            logger.warning(f"session trust ignored by no-trust mode: {tool_name}")
            return
        self.session_trust.add(tool_name)
        self.session_deny.discard(tool_name)

    def set_session_deny(self, tool_name: str) -> None:
        self.session_deny.add(tool_name)
        self.session_trust.discard(tool_name)

    def set_server_trust(self, server_name: str) -> None:
        """会话级 server 信任——server 内的全部 tool 在本 session 内直通。

        不写回 yaml，进程结束清空（与 session_trust/session_deny 同生命周期）。
        """
        if self.no_trust_mode:
            logger.warning(f"server trust ignored by no-trust mode: {server_name}")
            return
        self.server_trust.add(server_name)

    def clear_session(self) -> None:
        self.session_trust.clear()
        self.session_deny.clear()
        self.server_trust.clear()

    def set_permanent_trust(self, tool_name: str) -> None:
        """永久信任（写回 yaml）。"""
        tool_cfg = self.tools.setdefault(tool_name, {"risk": "MEDIUM"})
        tool_cfg["mode"] = "trust"

    def set_permanent_deny(self, tool_name: str) -> None:
        tool_cfg = self.tools.setdefault(tool_name, {"risk": "HIGH"})
        tool_cfg["mode"] = "deny"


def load_permissions(path: Optional[Path] = None) -> PermissionState:
    """从 yaml 读 → PermissionState。文件不存在或解析失败用 defaults。"""
    p = path or (CONFIG_DIR / "permissions.yaml")
    if not p.exists():
        logger.info(f"permissions.yaml not found at {p}, using defaults")
        return _state_from_dict(DEFAULT_PERMISSIONS)

    try:
        with open(p, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        logger.error(f"Failed to load permissions.yaml: {e}, using defaults")
        return _state_from_dict(DEFAULT_PERMISSIONS)

    # 与 defaults 合并（确保新增工具也能正常用）
    merged = _deep_merge(DEFAULT_PERMISSIONS, data)
    return _state_from_dict(merged)


def save_permissions(state: PermissionState, path: Optional[Path] = None) -> None:
    """写回 yaml。会话级 trust/deny 不写。"""
    p = path or (CONFIG_DIR / "permissions.yaml")

    out = {
        "mode": state.mode,
        "tools": state.tools,
        "path_rules": [
            {"match": r.pattern, "action": r.action, **({"operations": r.operations} if r.operations else {})}
            for r in state.path_rules
        ],
    }
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        yaml.safe_dump(out, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
    logger.info(f"permissions.yaml saved to {p}")


def _deep_merge(base: dict, overlay: dict) -> dict:
    """递归合并 overlay 到 base，返回新 dict（不修改输入）。"""
    out = dict(base)
    for k, v in overlay.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _state_from_dict(data: dict) -> PermissionState:
    mode = data.get("mode", "normal")
    tools = data.get("tools", {})
    rules = [PathRule(pattern=r["match"], action=r["action"],
                      operations=r.get("operations", []))
             for r in data.get("path_rules", [])]
    return PermissionState(mode=mode, tools=tools, path_rules=rules)

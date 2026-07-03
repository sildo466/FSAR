"""FSAR RiskEngine — produces a verdict before Tool.execute() runs.

Input:  tool instance + args (dict) + PermissionState
Output: RiskVerdict { action: proceed|confirm|deny, reason, rule_matched }

Decision order (first match wins):
1. Session / permanent deny              → DENY
2. blocked_patterns hits                 → DENY
3. path_rules matches a path             → DENY
4. effective_risk SAFE                   → PROCEED
5. yaml/session/server-trust mode        → PROCEED (unless session.mode = strict)
6. yaml mode = ask                       → CONFIRM (unless session.mode = trust)
7. tool not in yaml (mode=None)          → threshold check on effective_risk vs session.mode

Note: for dynamically-registered tools (MCP), PermissionState.tool_mode returns
None when the tool has no yaml entry and no session trust — step 7 then decides
based on its declared risk_level + the session-mode threshold, instead of being
unconditionally confirmed.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from typing import Optional

from src.security.permissions import PermissionState
from src.tools.registry import Tool

# Tool action name constants (used by risk routing / UI / audit)
SAFE = "SAFE"
LOW = "LOW"
MEDIUM = "MEDIUM"
HIGH = "HIGH"
CRITICAL = "CRITICAL"

# RiskRank — used for ordinal comparisons
_RISK_RANK = {SAFE: 0, LOW: 1, MEDIUM: 2, HIGH: 3, CRITICAL: 4}

# How different session.modes respond:
# strict: ask by default (overrides yaml 'trust' with confirm)
# normal: trust yaml, follow ask/deny as configured
# trust:  any tool marked trust in yaml passes through
_ALWAYS_ASK_ABOVE = {  # per session.mode, the threshold at which we ask
    "strict": LOW,      # LOW and above → ask
    "normal": HIGH,     # HIGH and above → ask
    "trust": CRITICAL,  # only CRITICAL → ask
}


@dataclass
class RiskVerdict:
    action: str  # "proceed" | "confirm" | "deny"
    reason: str
    rule_matched: Optional[str] = None
    effective_risk: str = SAFE

    def is_denied(self) -> bool:
        return self.action == "deny"

    def needs_confirm(self) -> bool:
        return self.action == "confirm"


class RiskEngine:
    def __init__(self, state: PermissionState):
        self.state = state

    def evaluate(self, tool: Tool, args: dict) -> RiskVerdict:
        name = tool.name
        # Optional server identity (MCPTool exposes this). None for builtin tools.
        server_name = getattr(tool, "server_name", None)

        # 1. deny takes priority
        tool_mode = self.state.tool_mode(
            name,
            operation=_extract_operation(tool, args),
            server_name=server_name,
        )
        if tool_mode == "deny":
            return RiskVerdict("deny", f"Tool '{name}' is permanently or session-deny-listed",
                               "deny_rule", self.state.tool_risk(name))

        # 2. blocked_patterns (searched in any string arg value)
        for pattern in self.state.blocked_patterns(name):
            for v in args.values():
                if isinstance(v, str) and _pattern_matches(pattern, v):
                    return RiskVerdict("deny", f"Matched blocked pattern: '{pattern}'",
                                       "blocked_pattern", self.state.tool_risk(name))

        # 3. path_rules
        for rule in self.state.path_rules:
            for v in args.values():
                if isinstance(v, str) and rule.matches(v):
                    return RiskVerdict("deny", f"Path matches rule '{rule.pattern}' (action={rule.action})",
                                       "path_rule", self.state.tool_risk(name))

        # 4-6. effective_risk evaluation
        # Priority: yaml entry (if present) > tool's own risk_level > MEDIUM.
        # If the tool is unknown to yaml, fall back to the tool's declared risk
        # so MCP tools use the risk_level from mcp_servers.yaml (not a silent
        # MEDIUM default).
        if name in self.state.tools:
            risk = self.state.tool_risk(name)
        else:
            risk = getattr(tool, "risk_level", MEDIUM) or MEDIUM
        risk_upper = risk.upper()
        effective_risk = risk_upper if risk_upper in _RISK_RANK else MEDIUM

        # SAFE always passes
        if effective_risk == SAFE:
            return RiskVerdict("proceed", "SAFE tool passes automatically", "safe_shortcut", SAFE)

        # trust mode passes (unless session.mode = strict)
        if tool_mode == "trust" and self.state.mode != "strict":
            return RiskVerdict("proceed", f"Tool '{name}' is in trust mode", "yaml_trust", effective_risk)

        # ask mode → CONFIRM, but session.mode=trust overrides (deny already caught above)
        if tool_mode == "ask":
            if self.state.mode == "trust":
                return RiskVerdict("proceed", f"Session mode=trust overrides per-tool ask",
                                   "session_trust_override", effective_risk)
            return RiskVerdict("confirm", f"Tool '{name}' is configured to require confirmation",
                               "yaml_ask", effective_risk)

        # Not in yaml → decide from effective_risk + session.mode
        threshold = _ALWAYS_ASK_ABOVE.get(self.state.mode, HIGH)
        if _RISK_RANK.get(effective_risk, _RISK_RANK[MEDIUM]) >= _RISK_RANK.get(threshold, _RISK_RANK[HIGH]):
            return RiskVerdict("confirm",
                               f"Default policy: risk level {effective_risk} >= {threshold} (mode={self.state.mode})",
                               "default_ask", effective_risk)

        return RiskVerdict("proceed", f"Risk level {effective_risk} is below threshold {threshold}",
                           "default_pass", effective_risk)


# ---------- helpers ----------

def _extract_operation(tool: Tool, args: dict) -> Optional[str]:
    """Extract an operation name from tool+args (used for multi-action tools like file_ops).

    Looks for an explicit `operation` arg, then falls back to a heuristic
    (e.g. the `edit` tool is treated as write).
    """
    if "operation" in args and isinstance(args["operation"], str):
        return args["operation"]
    if tool.name == "edit":
        return "write"
    return None


def _pattern_matches(pattern: str, value: str) -> bool:
    """Simple substring / wildcard matching:
    - Plain text → case-insensitive substring search
    - Contains * or ? → fnmatch
    """
    if any(c in pattern for c in "*?[]"):
        return fnmatch.fnmatch(value.lower(), pattern.lower())
    return pattern.lower() in value.lower()

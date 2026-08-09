"""Shared in-tool sandbox guard for builtin tools."""

from __future__ import annotations

from typing import Any


def guard_file_read(raw_path: str, config) -> str | None:
    from pathlib import Path
    from src.sandbox.sensitive import match_read_blacklist
    from src.skills.gate import gate_skill_read_path

    path = Path(raw_path).expanduser().resolve()
    blocked, _ = match_read_blacklist(path, config)
    if blocked:
        return "[BLOCKED: file_read_blacklist]"
    verification = gate_skill_read_path(path, config)
    if not verification.valid:
        return f"[BLOCKED: skill not reviewed ({verification.reason})]"
    return None


def _standalone_command_floor(command: str, shell: str, kwargs: dict[str, Any]) -> str | None:
    """Unconditional hardline command floor for callers without a sandbox session.

    Mirrors the hardline stage of WorkspaceGate.command_verdicts so that the CLI
    path (which has no workspace binding) still blocks disk destruction,
    fetch-and-execute, persistence and privilege-escalation commands instead of
    failing open.
    """
    from src.sandbox import hardline
    from src.utils.config import get_config

    config = kwargs.get("_security_config") or get_config()
    disabled = set(config.get("security.hardline_disabled_classes", []) or [])
    blocked, reason = hardline.check(command, shell, disabled)
    if blocked:
        return f"BLOCKED: sandbox hardline - {reason}"
    return None


def _standalone_path_floor(operation: str, raw_path: str, kwargs: dict[str, Any]) -> str | None:
    """Unconditional path floor for callers without a sandbox session.

    Mirrors the workspace-independent protections of WorkspaceGate.validate_path:
    the sensitive-path deny and the executable-write deny. Workspace confinement
    itself is a GUI concept and is not applied here.
    """
    if operation not in {"write", "edit", "move", "mkdir", "delete", "copy"}:
        return None
    from pathlib import Path

    from src.sandbox.sensitive import match as match_sensitive
    from src.utils.config import get_config

    config = kwargs.get("_security_config") or get_config()
    resolved = Path(raw_path).expanduser().resolve()
    custom = list(config.get("security.custom_sensitive_paths", []) or [])
    matched, reason = match_sensitive(resolved, custom_patterns=custom)
    if matched:
        return f"BLOCKED: sandbox hardline - sensitive path ({reason})"
    if operation in {"write", "edit", "move", "mkdir"} and resolved.suffix.lower() in {".exe", ".dll", ".com", ".scr", ".msi"}:
        return "BLOCKED: sandbox hardline - writing executable files is blocked"
    return None


async def guard_path(tool: str, operation: str, raw_path: str, kwargs: dict[str, Any]) -> str | None:
    if operation == "read":
        from src.utils.config import get_config
        config = kwargs.get("_security_config") or get_config()
        blocked = guard_file_read(raw_path, config)
        if blocked:
            return blocked
    if kwargs.get("_sandbox_prevalidated"):
        return None
    context = kwargs.get("session_ctx")
    if context is None:
        return _standalone_path_floor(operation, raw_path, kwargs)
    verdict = context.workspace_gate.validate_path(
        raw_path, workspace_id=context.active_workspace_id, operation=operation,
        session_id=context.session_id, conversation_id=context.conversation_id,
    )
    return await _resolve(context, tool, operation, verdict)


async def guard_command(command: str, shell: str, kwargs: dict[str, Any]) -> str | None:
    if kwargs.get("_sandbox_prevalidated"):
        return None
    context = kwargs.get("session_ctx")
    if context is None:
        return _standalone_command_floor(command, shell, kwargs)
    if hasattr(context.workspace_gate, "command_verdicts"):
        verdicts = context.workspace_gate.command_verdicts(
            command, workspace_id=context.active_workspace_id, shell=shell,
            session_id=context.session_id, conversation_id=context.conversation_id,
        )
    else:
        verdict = context.workspace_gate.check_command(
            command, workspace_id=context.active_workspace_id, shell=shell,
            session_id=context.session_id, conversation_id=context.conversation_id,
        )
        verdicts = [verdict] if verdict is not None else []
    for verdict in verdicts:
        result = await _resolve(context, "run_command", "execute", verdict)
        if result:
            return result
    return None


async def _resolve(context, tool: str, operation: str, verdict) -> str | None:
    if verdict.action == "deny":
        return f"BLOCKED: sandbox hardline - {verdict.reason}" if verdict.rule_matched == "hardline" else f"Error: sandbox denied - {verdict.reason}"
    if verdict.action == "confirm_escape":
        decision = await context.request_escape(tool, operation, verdict)
        if decision == "deny":
            return f"Error: sandbox escape denied - {verdict.reason}"
    return None

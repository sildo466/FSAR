# SPDX-License-Identifier: MIT
"""Workspace and sandbox security WebSocket messages."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import WebSocket

from src.sandbox.hardline import HARDLINE_CLASSES_ORDER, list_classes as list_hardline
from src.sandbox.sensitive import list_classes as list_sensitive


def snapshot(ctx: dict[str, Any], conversation_id: str | None = None) -> dict[str, Any]:
    repo = ctx.get("workspace_repo")
    config = ctx.get("config")
    if repo is None or config is None:
        return {}
    workspaces = [workspace.to_dict() for workspace in repo.list()]
    default = repo.get_default_for_new()
    current = None
    if conversation_id:
        binding = repo.get_binding(conversation_id)
        workspace = repo.get(binding[1]) if binding else None
        if workspace:
            current = {"conversation_id": conversation_id, "workspace": workspace.to_dict()}
    disabled = set(config.get("security.hardline_disabled_classes", []) or [])
    return {
        "workspace": {
            "current_binding": current,
            "default_workspace_id": default.id if default else None,
            "all_workspaces": workspaces,
        },
        "security": {
            "hardline_disabled_classes": sorted(disabled),
            "power_user_mode": bool(config.get("security.power_user_mode", False)),
            "hardline_classes": list_hardline(disabled),
        },
        "sensitive": {
            "classes": list_sensitive(),
            "custom": list(config.get("security.custom_sensitive_paths", []) or []),
        },
    }


async def dispatch(ws: WebSocket, msg: dict[str, Any], ctx: dict[str, Any]) -> bool:
    message_type = str(msg.get("type", ""))
    sandbox_message = message_type.startswith(("workspace.", "hardline.", "sensitive.", "sandbox_audit.", "tool.sandbox."))
    if not sandbox_message:
        return False
    repo = ctx.get("workspace_repo")
    config = ctx.get("config")
    if repo is None or config is None:
        await _error(ws, "sandbox_unavailable", "sandbox services are unavailable")
        return True
    if message_type == "tool.sandbox.escape_decision":
        ok = ctx["sandbox_bridge"].respond(str(msg.get("request_id", "")), str(msg.get("decision", "")))
        await ws.send_json({"type": "tool.sandbox.escape_ack", "request_id": msg.get("request_id"), "ok": ok})
        return True
    if message_type == "workspace.list":
        await ws.send_json({"type": "workspace.list_result", "workspaces": [item.to_dict() for item in repo.list()]})
        return True
    if message_type == "workspace.get":
        item = repo.get(int(msg.get("id", 0)))
        await ws.send_json({"type": "workspace.got", "workspace": item.to_dict() if item else None})
        return True
    if message_type == "workspace.create":
        try:
            root_path = _template_root(str(msg.get("template", "blank")), msg.get("root_path"), config)
            if not str(msg.get("name", "")).strip():
                raise ValueError("workspace name is required")
            Path(root_path).mkdir(parents=True, exist_ok=True)
            item = repo.create(
                name=str(msg.get("name", "")).strip(), root_path=root_path,
                allowed_paths=_string_list(msg.get("allowed_paths"), ["**"]),
                blocked_patterns=_string_list(msg.get("blocked_patterns"), []),
                set_default=bool(msg.get("set_default", False)),
            )
            await ws.send_json({"type": "workspace.created", "workspace": item.to_dict()})
        except Exception as exc:
            await _error(ws, "workspace_create", str(exc))
        return True
    if message_type == "workspace.update":
        try:
            fields = {key: msg[key] for key in ("name", "root_path", "allowed_paths", "blocked_patterns") if key in msg}
            if "root_path" in fields:
                Path(str(fields["root_path"])).expanduser().mkdir(parents=True, exist_ok=True)
            item = repo.update(int(msg.get("id", 0)), **fields)
            await ws.send_json({"type": "workspace.updated", "workspace": item.to_dict()})
        except Exception as exc:
            await _error(ws, "workspace_update", str(exc))
        return True
    if message_type == "workspace.delete":
        try:
            workspace_id = int(msg.get("id", 0))
            ok = repo.delete(workspace_id)
            await ws.send_json({"type": "workspace.deleted", "id": workspace_id, "ok": ok})
        except Exception as exc:
            await _error(ws, "workspace_delete", str(exc))
        return True
    if message_type == "workspace.set_default":
        try:
            workspace_id = int(msg.get("id", 0))
            repo.set_default_for_new(workspace_id)
            await ws.send_json({"type": "workspace.default_changed", "id": workspace_id})
        except Exception as exc:
            await _error(ws, "workspace_default", str(exc))
        return True
    if message_type in {"workspace.bind", "workspace.switch_binding"}:
        try:
            conversation_id = str(msg.get("conversation_id", ""))
            workspace_id = int(msg.get("workspace_id", 0))
            repo.bind(conversation_id, workspace_id)
            item = repo.get(workspace_id)
            await ws.send_json({
                "type": "workspace.binding_changed" if message_type.endswith("switch_binding") else "workspace.bound",
                "conversation_id": conversation_id, "workspace_id": workspace_id,
                "workspace": item.to_dict() if item else None,
            })
        except Exception as exc:
            await _error(ws, "workspace_bind", str(exc))
        return True
    if message_type == "workspace.get_binding":
        conversation_id = str(msg.get("conversation_id", ""))
        item = repo.get_or_create_binding(conversation_id)
        await ws.send_json({"type": "workspace.bound", "conversation_id": conversation_id, "workspace_id": item.id, "workspace": item.to_dict()})
        return True
    if message_type == "hardline.list_classes":
        disabled = set(config.get("security.hardline_disabled_classes", []) or [])
        await ws.send_json({"type": "hardline.classes_result", "classes": list_hardline(disabled)})
        return True
    if message_type in {"hardline.set_disabled", "hardline.restore_all"}:
        classes = [] if message_type.endswith("restore_all") else _string_list(msg.get("classes"), [])
        invalid = set(classes) - set(HARDLINE_CLASSES_ORDER)
        if invalid:
            await _error(ws, "hardline_classes", f"unknown classes: {sorted(invalid)}")
            return True
        config.patch("security.hardline_disabled_classes", classes)
        config.save()
        await ws.send_json({"type": "hardline.classes_result", "classes": list_hardline(set(classes))})
        return True
    if message_type == "sensitive.list":
        await ws.send_json({"type": "sensitive.list_result", "classes": list_sensitive(), "custom": list(config.get("security.custom_sensitive_paths", []) or [])})
        return True
    if message_type in {"sensitive.add_custom", "sensitive.remove_custom"}:
        pattern = str(msg.get("pattern", "")).strip()
        if not pattern or pattern == "**":
            await _error(ws, "sensitive_pattern", "pattern must be specific")
            return True
        custom = list(config.get("security.custom_sensitive_paths", []) or [])
        if message_type.endswith("add_custom") and pattern not in custom:
            custom.append(pattern)
        if message_type.endswith("remove_custom"):
            custom = [item for item in custom if item != pattern]
        config.patch("security.custom_sensitive_paths", custom)
        config.save()
        await ws.send_json({"type": "sensitive.custom_added" if message_type.endswith("add_custom") else "sensitive.custom_removed", "pattern": pattern})
        return True
    if message_type == "sensitive.report_missing":
        report_dir = Path("data/sandbox_reports")
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.json"
        report_path.write_text(json.dumps({"path": msg.get("path", ""), "context": msg.get("context", "")}, ensure_ascii=False, indent=2), encoding="utf-8")
        await ws.send_json({"type": "sensitive.reported", "path": str(report_path)})
        return True
    if message_type == "sandbox_audit.list":
        events = repo.list_audit(since=msg.get("since"), conversation_id=msg.get("conversation_id"), limit=int(msg.get("limit", 50)))
        await ws.send_json({"type": "sandbox_audit.list_result", "events": events})
        return True
    return False


def _template_root(template: str, root_path: Any, config) -> str:
    if template in {"user_home", "full_computer"} and not config.get("security.power_user_mode", False):
        raise ValueError("power user mode is required for this template")
    if template == "user_home":
        return str(Path.home())
    if template == "full_computer":
        return Path.cwd().anchor or os.path.abspath(os.sep)
    if not str(root_path or "").strip():
        raise ValueError("root_path is required")
    return str(root_path)


def _string_list(value: Any, default: list[str]) -> list[str]:
    if value is None:
        return list(default)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError("expected a list of strings")
    return value


async def _error(ws: WebSocket, code: str, message: str) -> None:
    await ws.send_json({"type": "error", "code": code, "message": message, "recoverable": True})

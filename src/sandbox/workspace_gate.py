"""Workspace-aware path and command policy evaluation."""

from __future__ import annotations

import fnmatch
import os
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from src.sandbox import hardline, sensitive
from src.sandbox.paths import is_inside, safe_resolve


@dataclass(frozen=True)
class PathVerdict:
    action: str
    reason: str
    rule_matched: str
    resolved_path: str
    workspace_root: str
    is_sensitive: bool = False


class SessionAllowCache:
    def __init__(self) -> None:
        self._entries: dict[str, set[tuple[str, str]]] = {}

    def allows(self, session_id: str | None, rule: str, path: str) -> bool:
        if not session_id:
            return False
        normalized = os.path.normcase(path)
        for saved_rule, prefix in self._entries.get(session_id, set()):
            normalized_prefix = os.path.normcase(prefix).rstrip("/\\")
            if saved_rule == rule and (
                normalized == normalized_prefix
                or normalized.startswith(normalized_prefix + os.sep)
            ):
                return True
        return False

    def allow(self, session_id: str | None, rule: str, path_prefix: str) -> None:
        if session_id:
            self._entries.setdefault(session_id, set()).add((rule, path_prefix))

    def clear(self, session_id: str) -> None:
        self._entries.pop(session_id, None)


class WorkspaceGate:
    def __init__(
        self,
        workspace_repo,
        session_allow_cache: SessionAllowCache | None = None,
        custom_sensitive_paths: list[str] | Callable[[], list[str]] | None = None,
        disabled_classes: set[str] | Callable[[], set[str]] | None = None,
        always_allow_paths: list[str] | Callable[[], list[str]] | None = None,
    ) -> None:
        self.workspace_repo = workspace_repo
        self.session_allow_cache = session_allow_cache or SessionAllowCache()
        self._custom_sensitive_paths = custom_sensitive_paths or []
        self._disabled_classes = disabled_classes or set()
        self._always_allow_paths = always_allow_paths or []

    @staticmethod
    def _value(value):
        return value() if callable(value) else value

    def validate_path(
        self, raw_path: str, *, workspace_id: int, operation: str,
        session_id: str | None = None, conversation_id: str | None = None,
    ) -> PathVerdict:
        workspace = self.workspace_repo.get(workspace_id)
        if workspace is None:
            return PathVerdict("deny", "workspace is not configured", "missing_workspace", "", "")
        root = safe_resolve(workspace.root_path)
        resolved = safe_resolve(raw_path, base=root)
        path_text = str(resolved)

        sensitive_match, sensitive_reason = sensitive.match(
            resolved, custom_patterns=list(self._value(self._custom_sensitive_paths)),
        )
        always_allowed = self._is_always_allowed(resolved)
        if sensitive_match and not always_allowed:
            return self._escape_or_proceed(
                "sensitive_path", sensitive_reason, path_text, str(root), session_id, True,
            )

        inside_workspace = is_inside(resolved, root)
        if not inside_workspace and always_allowed:
            return PathVerdict("proceed", "path is permanently allowed", "outside_workspace", path_text, str(root), sensitive_match)
        if not inside_workspace:
            return self._escape_or_proceed(
                "outside_workspace", "path is outside the active workspace",
                path_text, str(root), session_id, sensitive_match,
            )

        relative = resolved.relative_to(root).as_posix()
        for pattern in workspace.blocked_patterns:
            if fnmatch.fnmatch(relative, pattern):
                return PathVerdict("deny", f"blocked by workspace pattern: {pattern}", "blocked_pattern", path_text, str(root), sensitive_match)

        if workspace.allowed_paths != ["**"] and not any(
            fnmatch.fnmatch(relative, pattern) for pattern in workspace.allowed_paths
        ):
            return self._escape_or_proceed(
                "outside_allowed_paths", "path is outside the workspace allowlist",
                path_text, str(root), session_id, sensitive_match,
            )

        if operation in {"write", "edit", "move", "mkdir"} and resolved.suffix.lower() in {".exe", ".dll", ".com", ".scr", ".msi"}:
            return PathVerdict("deny", "writing executable files is blocked", "executable_write", path_text, str(root), sensitive_match)

        return PathVerdict("proceed", "path is within workspace policy", "", path_text, str(root), sensitive_match)

    def _escape_or_proceed(self, rule: str, reason: str, path: str, root: str,
                           session_id: str | None, is_sensitive: bool) -> PathVerdict:
        if self.session_allow_cache.allows(session_id, rule, path):
            return PathVerdict("proceed", "allowed for this session", rule, path, root, is_sensitive)
        return PathVerdict("confirm_escape", reason, rule, path, root, is_sensitive)

    def _is_always_allowed(self, path: Path) -> bool:
        normalized = str(path).replace("\\", "/").lower()
        for pattern in self._value(self._always_allow_paths):
            expanded_pattern = os.path.expandvars(os.path.expanduser(pattern))
            if "*" in expanded_pattern or "?" in expanded_pattern:
                expanded = expanded_pattern.replace("\\", "/").lower()
            else:
                expanded = str(safe_resolve(expanded_pattern)).replace("\\", "/").lower()
            if fnmatch.fnmatch(normalized, expanded):
                return True
        return False

    def check_command(
        self, command: str, *, workspace_id: int, shell: str,
        session_id: str | None = None, conversation_id: str | None = None,
    ) -> PathVerdict | None:
        verdicts = self.command_verdicts(
            command, workspace_id=workspace_id, shell=shell,
            session_id=session_id, conversation_id=conversation_id,
        )
        return next((verdict for verdict in verdicts if verdict.action != "proceed"), None)

    def command_verdicts(
        self, command: str, *, workspace_id: int, shell: str,
        session_id: str | None = None, conversation_id: str | None = None,
    ) -> list[PathVerdict]:
        workspace = self.workspace_repo.get(workspace_id)
        root = workspace.root_path if workspace else ""
        blocked, reason = hardline.check(command, shell, set(self._value(self._disabled_classes)))
        if blocked:
            return [PathVerdict("deny", reason, "hardline", "", root)]
        verdicts: list[PathVerdict] = []
        for token in extract_path_tokens(command, shell):
            verdict = self.validate_path(
                token, workspace_id=workspace_id, operation="execute",
                session_id=session_id, conversation_id=conversation_id,
            )
            verdicts.append(verdict)
        return verdicts


_WINDOWS_PATH = re.compile(r"(?i)(?:[a-z]:\\[^\s|;&]+|%[A-Z_]+%\\[^\s|;&]+|\$env:[A-Z_]+\\[^\s|;&]+|(?:\.\.\\|\.\\)[^\s|;&]+)")
_POSIX_PATH = re.compile(r"(?<![\w.-])(?:~|/|\./|\.\./)[^\s|;&]+")
_HOME_PATH = re.compile(r"(?<![\w.-])\$HOME(?:[/\\][^\s|;&]+)?")
_PARENT_PATH = re.compile(r"(?<![\w.])\.\.(?![\w.])")


def extract_path_tokens(command: str, shell: str) -> list[str]:
    path_source = re.sub(r"(?i)\b[a-z][a-z0-9+.-]*://[^\s|;&]+", "", command)
    found = (
        _WINDOWS_PATH.findall(path_source)
        + _POSIX_PATH.findall(path_source)
        + _HOME_PATH.findall(path_source)
        + _PARENT_PATH.findall(path_source)
    )
    try:
        for token in shlex.split(path_source, posix=shell == "bash"):
            cleaned = token.strip("'\"(),")
            if cleaned == ".." or cleaned.startswith(("/", "~/", "./", "../", ".\\", "..\\", "$HOME")) or re.match(r"(?i)^(?:[a-z]:[\\/]|\$env:[A-Z_]+[\\/])", cleaned):
                found.append(cleaned)
    except ValueError:
        pass
    result: list[str] = []
    for item in found:
        cleaned = item.rstrip("'\"),")
        if cleaned not in result:
            result.append(cleaned)
    return result

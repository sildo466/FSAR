"""Sensitive filesystem locations that always require confirmation."""

from __future__ import annotations

import fnmatch
import os
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SensitiveRule:
    class_id: str
    description: str
    match_dir: str | None = None
    match_filename: str | None = None
    match_glob: str | None = None
    platform: str = "any"


SENSITIVE_CLASSES: dict[str, tuple[SensitiveRule, ...]] = {
    "A": (
        SensitiveRule("A", "Cryptographic identity", match_dir=".ssh"),
        SensitiveRule("A", "Cryptographic identity", match_dir=".gnupg"),
        SensitiveRule("A", "Cryptographic identity", match_filename="id_rsa"),
        SensitiveRule("A", "Cryptographic identity", match_filename="id_ed25519"),
        SensitiveRule("A", "Cryptographic identity", match_filename="id_ecdsa"),
        SensitiveRule("A", "Cryptographic identity", match_glob="*.ppk"),
    ),
    "B": (
        SensitiveRule("B", "Cloud credentials", match_dir=".aws"),
        SensitiveRule("B", "Cloud credentials", match_dir=".azure"),
        SensitiveRule("B", "Cloud credentials", match_dir="gcloud"),
        SensitiveRule("B", "Cloud credentials", match_dir=".kube"),
        SensitiveRule("B", "Cloud credentials", match_filename=".netrc"),
        SensitiveRule("B", "Cloud credentials", match_glob="*/.docker/config.json"),
        SensitiveRule("B", "Cloud credentials", match_glob="*/gh/hosts.yml"),
    ),
    "C": (
        SensitiveRule("C", "Application secrets", match_filename=".env"),
        SensitiveRule("C", "Application secrets", match_filename=".env.local"),
        SensitiveRule("C", "Application secrets", match_filename=".env.production"),
        SensitiveRule("C", "Application secrets", match_filename=".env.development"),
        SensitiveRule("C", "Application secrets", match_filename=".env.test"),
        SensitiveRule("C", "Application secrets", match_filename=".envrc"),
        SensitiveRule("C", "Application secrets", match_glob="*.pem"),
        SensitiveRule("C", "Application secrets", match_glob="*.key"),
        SensitiveRule("C", "Application secrets", match_glob="*.p12"),
        SensitiveRule("C", "Application secrets", match_glob="*.pfx"),
        SensitiveRule("C", "Application secrets", match_glob="*.kdbx"),
        SensitiveRule("C", "Application secrets", match_filename="wallet.dat"),
        SensitiveRule("C", "Application secrets", match_glob="*/User Data/*/Login Data"),
    ),
    "D": (
        SensitiveRule("D", "System integrity anchors", match_filename="hosts"),
        SensitiveRule("D", "System integrity anchors", match_filename=".bashrc"),
        SensitiveRule("D", "System integrity anchors", match_filename=".zshrc"),
        SensitiveRule("D", "System integrity anchors", match_filename=".profile"),
        SensitiveRule("D", "System integrity anchors", match_glob="*PowerShell*profile.ps1", platform="windows"),
    ),
}
SENSITIVE_CLASSES_ORDER = tuple("ABCD")
SENSITIVE_LABELS = {key: rules[0].description for key, rules in SENSITIVE_CLASSES.items()}
DEFAULT_READ_BLACKLIST = [
    "~/.ssh/*",
    "~/.aws/credentials",
    "~/.gnupg/*",
    "*.key",
    "*.pem",
    "id_rsa",
]
_READ_COMMAND = re.compile(
    r"(?:^|[;&|]\s*)\b(?:cat|less|type|Get-Content)\s+(?:-[A-Za-z]+\s+)*(?:['\"]([^'\"]+)['\"]|([^\s;&|]+))",
    re.IGNORECASE,
)


def _matches_glob(path: Path, pattern: str) -> bool:
    normalized = str(path).replace("\\", "/")
    expanded = os.path.expandvars(os.path.expanduser(pattern)).replace("\\", "/")
    return fnmatch.fnmatch(normalized.lower(), expanded.lower()) or fnmatch.fnmatch(path.name.lower(), pattern.lower())


def match(resolved_path: Path, platform: str | None = None,
          custom_patterns: list[str] | None = None) -> tuple[bool, str]:
    platform_name = platform or ("windows" if os.name == "nt" else "posix")
    parts = {part.lower() for part in resolved_path.parts}
    filename = resolved_path.name.lower()
    for class_id in SENSITIVE_CLASSES_ORDER:
        for rule in SENSITIVE_CLASSES[class_id]:
            if rule.platform not in ("any", platform_name):
                continue
            if rule.match_dir and rule.match_dir.lower() in parts:
                return True, f"class {class_id} - {rule.description}"
            if rule.match_filename and filename == rule.match_filename.lower():
                if filename != "hosts" or _is_hosts_path(resolved_path):
                    return True, f"class {class_id} - {rule.description}"
            if rule.match_glob and _matches_glob(resolved_path, rule.match_glob):
                return True, f"class {class_id} - {rule.description}"
    for pattern in custom_patterns or []:
        if _matches_glob(resolved_path, pattern):
            return True, f"custom sensitive path - {pattern}"
    return False, ""


def match_read_blacklist(resolved_path: Path, config) -> tuple[bool, str]:
    if not config.get("security.file_read_blacklist.enabled", True):
        return False, ""
    patterns: list[str] = []
    if config.get("security.file_read_blacklist.defaults", True):
        patterns.extend(DEFAULT_READ_BLACKLIST)
    patterns.extend(config.get("security.file_read_blacklist.extra_patterns", []) or [])
    for pattern in patterns:
        if isinstance(pattern, str) and _matches_glob(resolved_path, pattern):
            return True, pattern
    return False, ""


def command_reads_blacklisted(command: str, cwd: Path, config) -> bool:
    for match in _READ_COMMAND.finditer(command):
        raw_path = match.group(1) or match.group(2)
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = cwd / candidate
        if match_read_blacklist(candidate.resolve(), config)[0]:
            return True
        from src.skills.gate import gate_skill_read_path
        if not gate_skill_read_path(candidate.resolve(), config).valid:
            return True
    return False


def _is_hosts_path(path: Path) -> bool:
    normalized = str(path).replace("\\", "/").lower()
    return normalized.endswith("/etc/hosts") or normalized.endswith("/system32/drivers/etc/hosts")


def list_classes() -> list[dict]:
    return [
        {"id": class_id, "label": SENSITIVE_LABELS[class_id], "pattern_count": len(SENSITIVE_CLASSES[class_id])}
        for class_id in SENSITIVE_CLASSES_ORDER
    ]

"""Unconditional command safety floor."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class HardlineRule:
    class_id: str
    description: str
    patterns: tuple[tuple[str, frozenset[str]], ...]


_ALL = frozenset({"powershell", "cmd", "bash"})
_WIN = frozenset({"powershell", "cmd"})
_PS = frozenset({"powershell"})
_BASH = frozenset({"bash"})

HARDLINE_CLASSES: dict[str, tuple[HardlineRule, ...]] = {
    "A": (HardlineRule("A", "Disk destruction", (
        (r"\brm\s+-(?=[^\s]*r)(?=[^\s]*f)[^\s]+\s+(?:--\s+)?(?:/|~)(?:\s|$)", _BASH),
        (r"\b(?:mkfs(?:\.\w+)?|fdisk)\s+/dev/", _BASH),
        (r"\bformat\s+[a-z]:", _WIN),
        (r"\bdiskpart\b[^\r\n]*(?:\bclean\b|/s)", _WIN),
        (r"\b(?:vssadmin\s+delete\s+shadows|wbadmin\s+delete\s+catalog|reagentc\s+/disable|cipher\s+/w:|sdelete\b|shred\s+-)", _ALL),
        (r"\bdel\s+/f\s+/s\s+[a-z]:\\", _WIN),
    )),),
    "B": (HardlineRule("B", "System lifecycle", (
        (r"(?:^|[;&|]\s*)\b(?:shutdown|reboot|poweroff|halt)(?:\s|$)", _ALL),
        (r"\binit\s+[06]\b|\bsystemctl\s+(?:reboot|poweroff)\b|\bloginctl\s+reboot\b", _BASH),
        (r"\b(?:Stop-Computer|Restart-Computer)\b", _PS),
    )),),
    "C": (HardlineRule("C", "Persistence or autostart", (
        (r"\breg\s+add\s+[^\r\n]*(?:\\Run|\\RunOnce)\b", _WIN),
        (r"\bsc(?:\.exe)?\s+create\b|\bschtasks\s+/create\b[^\r\n]*/ru\s+(?:SYSTEM|Administrator)", _WIN),
        (r"\bcrontab\s+-e\b|\bsystemctl\s+enable\b", _BASH),
        (r"\bbcdedit\s+/(?:set|deletevalue)\b", _WIN),
    )),),
    "D": (HardlineRule("D", "Privilege escalation", (
        (r"\bnet\s+user\s+[^\r\n]+/add\b|\bnet\s+localgroup\s+administrators\b[^\r\n]+/add\b", _WIN),
        (r"\b(?:Add-LocalGroupMember|New-LocalUser)\b|\brunas\s+/user:Administrator\b", _WIN),
        (r"\busermod\s+-aG\s+sudo\b|\bsudo\s+-i\b", _BASH),
    )),),
    "E": (HardlineRule("E", "Resource exhaustion", (
        (r":\s*\(\s*\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:", _BASH),
        (r"%0\s*\|\s*%0", _WIN),
        (r"\bwhile\s+true\s*;\s*do\b", _BASH),
    )),),
    "F": (HardlineRule("F", "Service or daemon control", (
        (r"\b(?:Stop-Service|Set-Service\s+[^\r\n]*-StartupType\s+Disabled)\b", _PS),
        (r"\bsystemctl\s+(?:stop|disable)\b|\bkill\s+-9\s+1\b|\bkillall\s+init\b", _BASH),
        (r"\bsc(?:\.exe)?\s+(?:stop|start|config)\b|\btaskkill\s+/f\s+/im\s+(?:lsass|winlogon|csrss)\.exe", _WIN),
    )),),
    "G": (HardlineRule("G", "Network security configuration", (
        (r"\bnetsh\s+advfirewall\s+set\s+allprofiles\s+state\s+off\b", _WIN),
        (r"\biptables\s+(?:-F|-P\s+INPUT\s+ACCEPT)\b|\bufw\s+disable\b|\bfirewall-cmd\b", _BASH),
        (r"\broute\s+(?:add|del)\b|\bip\s+link\s+set\b[^\r\n]*\bdown\b", _ALL),
    )),),
    "H": (HardlineRule("H", "Fetch and execute", (
        (r"\b(?:curl|wget)\b[^\r\n|]*\|\s*(?:ba)?sh\b", _BASH),
        (r"\b(?:curl|wget|iwr|Invoke-WebRequest)\b[^\r\n|]*\|\s*(?:powershell|pwsh|iex|Invoke-Expression)\b", _WIN),
        (r"\bInvoke-Expression\b[^\r\n]*(?:DownloadString|Invoke-WebRequest)", _PS),
        (r"\bmsiexec(?:\.exe)?\s+/i\s+https?://", _WIN),
    )),),
    "I": (HardlineRule("I", "Filesystem integrity", (
        (r"\btakeown\s+/f\s+(?:[a-z]:\\Windows|/)[^\r\n]*/r\b", _WIN),
        (r"\bicacls\s+(?:[a-z]:\\Windows|[a-z]:\\Program Files)[^\r\n]*/grant\s+Everyone:F[^\r\n]*/t\b", _WIN),
        (r"\bchmod\s+-R\s+777\s+/(?:\s|$)", _BASH),
        (r"\bSet-Acl\b|\battrib\s+-s\s+-h\s+-r\b", _WIN),
    )),),
}

HARDLINE_CLASSES_ORDER = tuple("ABCDEFGHI")
HARDLINE_LABELS = {key: rules[0].description for key, rules in HARDLINE_CLASSES.items()}


def check(command: str, shell: str, disabled_classes: set[str] | None = None) -> tuple[bool, str]:
    disabled = disabled_classes or set()
    shell_name = shell.lower()
    normalized = unicodedata.normalize("NFKC", command)
    normalized = "".join(ch for ch in normalized if ch not in {"\u200b", "\u200c", "\u200d", "\ufeff", "\u2060"})
    normalized = normalized.replace("`\n", " ").replace("^\n", " ")
    for class_id in HARDLINE_CLASSES_ORDER:
        if class_id in disabled:
            continue
        for rule in HARDLINE_CLASSES[class_id]:
            for pattern, shells in rule.patterns:
                if shell_name in shells and re.search(pattern, normalized, re.IGNORECASE):
                    return True, f"class {class_id} - {rule.description}"
    return False, ""


def list_classes(disabled_classes: set[str] | None = None) -> list[dict]:
    disabled = disabled_classes or set()
    return [
        {
            "id": class_id,
            "label": HARDLINE_LABELS[class_id],
            "enabled": class_id not in disabled,
            "pattern_count": sum(len(rule.patterns) for rule in HARDLINE_CLASSES[class_id]),
        }
        for class_id in HARDLINE_CLASSES_ORDER
    ]

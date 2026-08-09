from __future__ import annotations

import fnmatch
import ipaddress
import re
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

from src.utils.logger import logger


_URL_PATTERN = re.compile(r"https?://[^\s'\"<>]+", re.IGNORECASE)
_NETWORK_COMMAND_PATTERN = re.compile(
    r"\b(?:curl|wget|Invoke-WebRequest|iwr)\b[^\r\n;&|]*?((?:https?://)?[A-Za-z0-9.-]+(?::\d+)?(?:/[^\s'\";&|]*)?)",
    re.IGNORECASE,
)


class EgressDenied(PermissionError):
    pass


@dataclass(frozen=True)
class EgressDecision:
    allowed: bool
    reason: str


def check_url(url: str, config) -> EgressDecision:
    if not config.get("security.egress.enabled", False):
        return EgressDecision(True, "disabled")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return EgressDecision(False, "invalid_url")
    host = parsed.hostname.lower().rstrip(".")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    blocklist = config.get("security.egress.blocklist", []) or []
    allowlist = config.get("security.egress.allowlist", []) or []

    resolved_addresses = _resolve_addresses(host, port)
    if any(_matches(host, port, str(rule), resolved_addresses) for rule in blocklist):
        decision = EgressDecision(False, f"blocklist:{host}:{port}")
    elif allowlist and not any(
        _matches(host, port, str(rule), resolved_addresses) for rule in allowlist
    ):
        decision = EgressDecision(False, f"not_allowlisted:{host}:{port}")
    else:
        decision = EgressDecision(True, "allowed")

    if not decision.allowed and str(config.get("security.egress.mode", "deny")) == "warn":
        logger.warning(f"egress warning: {decision.reason}")
        return EgressDecision(True, f"warn:{decision.reason}")
    return decision


def enforce_url(url: str, config) -> None:
    decision = check_url(url, config)
    if not decision.allowed:
        raise EgressDenied(decision.reason)


def check_command(command: str, config) -> EgressDecision:
    urls = list(_URL_PATTERN.findall(command))
    for match in _NETWORK_COMMAND_PATTERN.finditer(command):
        target = match.group(1)
        if target and target not in urls:
            urls.append(target if target.startswith(("http://", "https://")) else "https://" + target)
    for url in urls:
        decision = check_url(url.rstrip("),;"), config)
        if not decision.allowed:
            return decision
    return EgressDecision(True, "no_blocked_url")


def _matches(host: str, port: int, rule: str, resolved_addresses: set[str]) -> bool:
    normalized = rule.strip().lower()
    if not normalized:
        return False
    try:
        network = ipaddress.ip_network(normalized, strict=False)
        return any(ipaddress.ip_address(address) in network for address in resolved_addresses)
    except ValueError:
        pass
    rule_host = normalized
    rule_port: int | None = None
    if ":" in normalized and normalized.rsplit(":", 1)[1].isdigit():
        rule_host, raw_port = normalized.rsplit(":", 1)
        rule_port = int(raw_port)
    if rule_port is not None and rule_port != port:
        return False
    return fnmatch.fnmatchcase(host, rule_host)


def _resolve_addresses(host: str, port: int) -> set[str]:
    try:
        return {
            item[4][0]
            for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        }
    except socket.gaierror:
        return {host}

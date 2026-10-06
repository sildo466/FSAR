# SPDX-License-Identifier: MIT
"""LAN management, exposed to the GUI over the loopback websocket.

Everything here is a local-user action: block an address, move a credential's
address anchor, read the identity audit. None of it exists on the LAN app — a
member cannot reach any of these message types.
"""

from __future__ import annotations

from typing import Any

from src.security.lan_tls import local_ipv4_addresses
from src.utils.logger import logger

_supervisor: Any = None
_blocklist: Any = None
_audit: Any = None
_tokens: Any = None


def set_engine(supervisor: Any, blocklist: Any, audit: Any, tokens: Any) -> None:
    global _supervisor, _blocklist, _audit, _tokens
    _supervisor = supervisor
    _blocklist = blocklist
    _audit = audit
    _tokens = tokens


def _agent_md_hint(port: int) -> str:
    """The line the owner hands to a member. No credential in it: the token is
    typed in from the one-time display, never copied out of here."""
    return (
        'curl -k -H "Authorization: Bearer $FSAR_ROOM_TOKEN" '
        f"https://<this-host>:{port}/room/agent.md"
    )


def _status_payload() -> dict[str, Any]:
    status = (
        dict(_supervisor.status()) if _supervisor is not None
        else {
            "listening": False, "host": "", "port": 0, "fingerprint": "",
            "lan_rooms": 0, "error": "not wired",
        }
    )
    port = int(status.get("port", 0) or 0)
    status["type"] = "lan.status.ok"
    status["addresses"] = [
        f"https://{host}:{port}" for host in local_ipv4_addresses()
    ]
    status["agent_md_hint"] = _agent_md_hint(port)
    return status


def _blocklist_payload() -> dict[str, Any]:
    entries = _blocklist.list() if _blocklist is not None else []
    return {"type": "lan.blocklist.ok", "entries": entries}


async def _reject(ws: Any, code: str, message: str) -> None:
    await ws.send_json({"type": "lan.error", "code": code, "message": message})


async def dispatch(ws: Any, msg: dict[str, Any]) -> bool:
    t = msg.get("type")
    if not isinstance(t, str) or not (
        t.startswith("lan.") or t == "auth_audit.list"
    ):
        return False
    if _supervisor is None:
        return False
    try:
        if t == "lan.status":
            await ws.send_json(_status_payload())
            return True

        if t == "lan.blocklist":
            await ws.send_json(_blocklist_payload())
            return True

        if t == "lan.block_ip":
            ip = str(msg.get("ip", "")).strip()
            if not ip:
                await _reject(ws, "bad_ip", "An address is required.")
                return True
            _blocklist.add(ip, reason=str(msg.get("reason", "")))
            await ws.send_json(_blocklist_payload())
            return True

        if t == "lan.unblock_ip":
            _blocklist.remove(str(msg.get("ip", "")).strip())
            await ws.send_json(_blocklist_payload())
            return True

        if t == "lan.rebind_ip":
            ip = str(msg.get("ip", "")).strip()
            if not ip:
                await _reject(ws, "bad_ip", "An address is required.")
                return True
            _tokens.rebind_ip(int(msg["token_id"]), ip)
            await ws.send_json(_status_payload())
            return True

        if t == "auth_audit.list":
            await ws.send_json({
                "type": "auth_audit.list.ok",
                "events": _audit.list(
                    limit=int(msg.get("limit") or 100),
                    room_id=msg.get("room_id"),
                ),
            })
            return True
    except Exception as e:
        logger.warning(f"{t} failed: {e}")
        try:
            await ws.send_json({
                "type": "lan.error", "code": "lan_handler", "message": str(e),
            })
        except Exception:
            pass
        return True

    return False

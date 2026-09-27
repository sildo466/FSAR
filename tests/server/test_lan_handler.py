# SPDX-License-Identifier: MIT
"""The GUI's view of the LAN listener: local-only management messages."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from src.server.handlers import lan as lan_handler


class FakeWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send_json(self, message: dict) -> None:
        self.messages.append(message)


def _wire(*, listening: bool = True, error: str = ""):
    status = {
        "listening": listening, "host": "0.0.0.0", "port": 8766,
        "fingerprint": "AB:CD", "lan_rooms": 1, "error": error,
    }
    supervisor = SimpleNamespace(
        sync=lambda: status, status=lambda: status,
    )
    entries: list[dict] = []

    def add(ip, *, reason=""):
        entries.append({"ip": ip, "reason": reason, "created_at": "t"})
        return True

    blocklist = SimpleNamespace(
        add=add, remove=lambda ip: True, list=lambda: list(entries),
    )
    rebound: list[tuple[int, str]] = []
    tokens = SimpleNamespace(
        rebind_ip=lambda token_id, ip: (rebound.append((token_id, ip)) or True),
    )
    events: list[dict] = []
    audit = SimpleNamespace(list=lambda limit=100, room_id=None: list(events))
    lan_handler.set_engine(supervisor, blocklist, audit, tokens)
    return SimpleNamespace(
        blocklist=blocklist, audit=audit, tokens=tokens, rebound=rebound,
        entries=entries, events=events,
    )


def test_status_reports_the_listener(tmp_path) -> None:
    _wire()
    ws = FakeWebSocket()
    asyncio.run(lan_handler.dispatch(ws, {"type": "lan.status"}))
    payload = ws.messages[-1]
    assert payload["type"] == "lan.status.ok"
    assert payload["listening"] is True
    assert payload["port"] == 8766
    assert payload["fingerprint"] == "AB:CD"
    assert payload["lan_rooms"] == 1


def test_status_offers_the_handoff_line_and_the_addresses() -> None:
    _wire()
    ws = FakeWebSocket()
    asyncio.run(lan_handler.dispatch(ws, {"type": "lan.status"}))
    payload = ws.messages[-1]
    assert "curl -k" in payload["agent_md_hint"]
    assert "/room/agent.md" in payload["agent_md_hint"]
    assert "$FSAR_ROOM_TOKEN" in payload["agent_md_hint"]
    assert payload["addresses"], "the owner needs an address to hand over"
    assert all(url.startswith("https://") for url in payload["addresses"])


def test_the_handoff_line_never_carries_a_credential() -> None:
    _wire()
    ws = FakeWebSocket()
    asyncio.run(lan_handler.dispatch(ws, {"type": "lan.status"}))
    payload = ws.messages[-1]
    # The placeholder is the whole point: the real token is typed by the owner.
    assert "$FSAR_ROOM_TOKEN" in payload["agent_md_hint"]
    assert "token_id" not in payload["agent_md_hint"]


def test_a_listener_error_is_surfaced() -> None:
    _wire(listening=False, error="OSError: address in use")
    ws = FakeWebSocket()
    asyncio.run(lan_handler.dispatch(ws, {"type": "lan.status"}))
    assert ws.messages[-1]["error"] == "OSError: address in use"


def test_block_ip_returns_the_new_list() -> None:
    _wire()
    ws = FakeWebSocket()
    asyncio.run(lan_handler.dispatch(
        ws, {"type": "lan.block_ip", "ip": "192.168.1.20", "reason": "noise"},
    ))
    payload = ws.messages[-1]
    assert payload["type"] == "lan.blocklist.ok"
    assert payload["entries"][0] == {
        "ip": "192.168.1.20", "reason": "noise", "created_at": "t",
    }


def test_block_ip_rejects_a_blank_address() -> None:
    _wire()
    ws = FakeWebSocket()
    asyncio.run(lan_handler.dispatch(ws, {"type": "lan.block_ip", "ip": "   "}))
    assert ws.messages[-1]["type"] == "lan.error"
    assert ws.messages[-1]["code"] == "bad_ip"


def test_block_ip_trims_the_address() -> None:
    wired = _wire()
    ws = FakeWebSocket()
    asyncio.run(lan_handler.dispatch(
        ws, {"type": "lan.block_ip", "ip": "  192.168.1.20  "},
    ))
    assert wired.entries[0]["ip"] == "192.168.1.20"


def test_unblock_returns_the_new_list() -> None:
    _wire()
    ws = FakeWebSocket()
    asyncio.run(lan_handler.dispatch(
        ws, {"type": "lan.unblock_ip", "ip": "192.168.1.20"},
    ))
    assert ws.messages[-1]["type"] == "lan.blocklist.ok"
    assert ws.messages[-1]["entries"] == []


def test_blocklist_lists_what_is_there() -> None:
    wired = _wire()
    wired.entries.append({"ip": "10.0.0.9", "reason": "", "created_at": "t"})
    ws = FakeWebSocket()
    asyncio.run(lan_handler.dispatch(ws, {"type": "lan.blocklist"}))
    assert ws.messages[-1]["entries"][0]["ip"] == "10.0.0.9"


def test_rebind_calls_the_store_and_reports_status() -> None:
    wired = _wire()
    ws = FakeWebSocket()
    asyncio.run(lan_handler.dispatch(
        ws, {"type": "lan.rebind_ip", "token_id": 4, "ip": "10.0.0.9"},
    ))
    assert wired.rebound == [(4, "10.0.0.9")]
    assert ws.messages[-1]["type"] == "lan.status.ok"


def test_rebind_rejects_a_blank_address() -> None:
    wired = _wire()
    ws = FakeWebSocket()
    asyncio.run(lan_handler.dispatch(
        ws, {"type": "lan.rebind_ip", "token_id": 4, "ip": ""},
    ))
    assert ws.messages[-1]["type"] == "lan.error"
    assert ws.messages[-1]["code"] == "bad_ip"
    assert wired.rebound == []


def test_audit_list_returns_events() -> None:
    wired = _wire()
    wired.events.append({"seq": 1, "action": "lan_auth", "result": "deny",
                         "reason": "ip_mismatch", "source_ip": "10.0.0.9"})
    ws = FakeWebSocket()
    asyncio.run(lan_handler.dispatch(ws, {"type": "auth_audit.list"}))
    payload = ws.messages[-1]
    assert payload["type"] == "auth_audit.list.ok"
    assert payload["events"][0]["reason"] == "ip_mismatch"


def test_an_unrelated_message_is_not_claimed() -> None:
    _wire()
    ws = FakeWebSocket()
    assert asyncio.run(lan_handler.dispatch(ws, {"type": "group.list"})) is False
    assert ws.messages == []


def test_nothing_is_claimed_before_the_engine_is_wired(monkeypatch) -> None:
    monkeypatch.setattr(lan_handler, "_supervisor", None)
    ws = FakeWebSocket()
    assert asyncio.run(lan_handler.dispatch(ws, {"type": "lan.status"})) is False

"""E2E smoke test: walk the wizard, switch character + user cards, upload + fetch avatar.

Runs against a backend already listening on http://127.0.0.1:8765.
Exits non-zero on any unexpected response.
"""
from __future__ import annotations

import io
import json
import struct
import sys
import urllib.request
import urllib.error
import zlib
import asyncio
import websockets

BASE = "http://127.0.0.1:8765"
WS = "ws://127.0.0.1:8765/ws"


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def ok(msg: str) -> None:
    print(f"  ok: {msg}")


def step(msg: str) -> None:
    print(f"\n=== {msg} ===")


# --- minimal PNG (1x1 red pixel) generator so we don't depend on a real file ---
def make_png(width: int = 256, height: int = 256) -> bytes:
    """Create a tiny synthetic PNG with width x height pixels of solid color."""
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # RGB
    # solid red pixel data
    raw = b""
    for _ in range(height):
        raw += b"\x00" + b"\xff\x00\x00" * width
    idat = zlib.compress(raw)
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


async def main() -> None:
    # 0. Health check
    step("0. Backend health")
    try:
        urllib.request.urlopen(f"{BASE}/health", timeout=5)
        ok("backend responding")

        # 0a. Check avatar endpoint shape with a real card_id (use id=1 from builtin seed)
        # First list cards to find a real id
    except urllib.error.URLError as e:
        fail(f"backend not reachable: {e}")

    async with websockets.connect(WS, open_timeout=5) as ws:
        # 1. Initial snapshot
        step("1. Initial WS snapshot")
        snap_raw = await asyncio.wait_for(ws.recv(), timeout=5)
        snap = json.loads(snap_raw)
        if snap.get("type") != "snapshot":
            fail(f"first message not snapshot: {snap.get('type')}")
        ob = snap.get("onboarding", {})
        ok(f"snapshot received; onboarding.required={ob.get('required')}")
        await _consume_until(ws, "conversation.list", lambda m: m.get("type") in ("conversation.created", "conversation.list"))

        # 2. Walk the wizard
        step("2. Wizard walk (provider → embedding → user_card → character_card)")
        await ws.send(json.dumps({"type": "provider.test_connection", "preset_id": "openai", "base_url": "https://api.openai.com/v1", "api_key": "sk-fake", "model": "gpt-4o-mini"}))
        await _wait_for(ws, "provider.test_result", timeout=5)
        ok("provider.test_connection responded")

        await ws.send(json.dumps({"type": "provider.create_builtin", "preset_id": "openai", "label": "openai", "api_key": "sk-fake", "base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini", "pricing": None}))
        await _wait_for(ws, "provider.created", timeout=5)
        ok("provider.create_builtin responded")

        for step_name in ("provider", "embedding", "user_card", "character_card"):
            await ws.send(json.dumps({"type": "onboarding.complete_step", "step": step_name, "data": {}}))
            await _wait_for(ws, "onboarding.step_completed", timeout=5)
            ok(f"onboarding.complete_step({step_name})")

        await ws.send(json.dumps({"type": "onboarding.complete"}))
        await _wait_for(ws, "onboarding.completed", timeout=5)
        ok("onboarding.complete → completed")

        # 3. List built-in cards (should be 6 character + 1 user)
        step("3. Built-in cards seeded")
        await ws.send(json.dumps({"type": "card.list", "kind": "character"}))
        chars_msg = await _wait_for(ws, "card.list_result", timeout=5, kind="character")
        chars = chars_msg.get("cards", [])
        if len(chars) < 6:
            fail(f"expected >=6 character cards (built-ins), got {len(chars)}: {[c['name'] for c in chars]}")
        ok(f"{len(chars)} character cards: {[c['name'] for c in chars]}")
        ids = [c["id"] for c in chars]
        target_char_id = next((c["id"] for c in chars if c["name"] == "FSAR-en"), None)
        other_char_id = next((c["id"] for c in chars if c["name"] == "FSAR-zh"), None)
        if not target_char_id or not other_char_id:
            fail("FSAR-en or FSAR-zh missing")
        ok(f"target=FSAR-en(id={target_char_id}) other=FSAR-zh(id={other_char_id})")

        await ws.send(json.dumps({"type": "card.list", "kind": "user"}))
        users_msg = await _wait_for(ws, "card.list_result", timeout=5, kind="user")
        users = users_msg.get("cards", [])
        ok(f"{len(users)} user cards")

        # 4. Create a new conversation, then switch character
        step("4. Create conversation + switch character")
        await ws.send(json.dumps({"type": "conversation.create"}))
        await _wait_for(ws, "conversation.created", timeout=5)
        # fetch sessions to get id
        await ws.send(json.dumps({"type": "conversation.list", "limit": 10}))
        list_msg = await _wait_for(ws, "conversation.list", timeout=5)
        sess_id = list_msg["sessions"][0]["id"]
        ok(f"conversation created: id={sess_id}")

        await ws.send(json.dumps({
            "type": "card.set_session_character",
            "session_id": sess_id,
            "character_id": target_char_id,
        }))
        ack = await _wait_for(ws, "card.session_character_set", timeout=5)
        if ack.get("character_id") != target_char_id:
            fail(f"session_character_set returned wrong id: {ack}")
        ok(f"set_session_character → FSAR-en({target_char_id})")

        # 5. Verify backend reads the right character for this session
        step("5. Backend can read session.character_id")
        await ws.send(json.dumps({
            "type": "card.list_session_character",
            "session_id": sess_id,
        }))
        read = await _wait_for(ws, "card.session_character", timeout=5)
        if read.get("character_id") != target_char_id:
            fail(f"list_session_character mismatch: expected {target_char_id} got {read.get('character_id')}")
        ok(f"list_session_character confirms FSAR-en({target_char_id})")

        # 6. Switch to a DIFFERENT character and verify the change
        step("6. Switch character to FSAR-zh")
        await ws.send(json.dumps({
            "type": "card.set_session_character",
            "session_id": sess_id,
            "character_id": other_char_id,
        }))
        await _wait_for(ws, "card.session_character_set", timeout=5)

        await ws.send(json.dumps({
            "type": "card.list_session_character",
            "session_id": sess_id,
        }))
        read2 = await _wait_for(ws, "card.session_character", timeout=5)
        if read2.get("character_id") != other_char_id:
            fail(f"after switch: expected {other_char_id} got {read2.get('character_id')}")
        ok(f"switch confirmed: FSAR-en({target_char_id}) → FSAR-zh({other_char_id})")

        # 7. Switch user card
        step("7. Switch default user card")
        user_id = users[0]["id"] if users else None
        if not user_id:
            fail("no user card to test")
        await ws.send(json.dumps({"type": "card.set_default", "kind": "user", "id": user_id}))
        ack_u = await _wait_for(ws, "card.default_changed", timeout=5)
        if ack_u.get("id") != user_id:
            fail(f"user default_changed wrong: {ack_u}")
        ok(f"user default → {user_id}")

        # 8. Upload avatar to a character card
        step("8. Upload avatar (POST /api/card/{id}/avatar)")
        png_bytes = make_png()
        req = urllib.request.Request(
            f"{BASE}/api/card/{target_char_id}/avatar",
            data=png_bytes,
            headers={"Content-Type": "application/octet-stream", "X-FSAR-Avatar-Ext": "png"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            if r.status != 200:
                fail(f"upload returned {r.status}")
            resp = json.loads(r.read())
            ok(f"uploaded → {resp.get('avatar_path')}")

        # 9. Fetch avatar back
        step("9. Fetch avatar (GET /api/card/{id}/avatar)")
        with urllib.request.urlopen(f"{BASE}/api/card/{target_char_id}/avatar", timeout=10) as r:
            if r.status != 200:
                fail(f"fetch returned {r.status}")
            content_type = r.headers.get("Content-Type", "")
            fetched = r.read()
            if not fetched:
                fail("fetched avatar empty")
            if "image" not in content_type:
                fail(f"unexpected content-type: {content_type}")
            ok(f"fetched {len(fetched)} bytes; content-type={content_type}")

        # 10. Verify avatar_path in card.list_result
        step("10. Avatar path reflected in card.list_result")
        await ws.send(json.dumps({"type": "card.list", "kind": "character"}))
        chars_msg2 = await _wait_for(ws, "card.list_result", timeout=5, kind="character")
        ch = next((c for c in chars_msg2["cards"] if c["id"] == target_char_id), None)
        if not ch or not ch.get("avatar_path"):
            fail(f"card list doesn't have avatar_path: {ch}")
        ok(f"avatar_path in list: {ch['avatar_path']}")

        print("\n=== ALL E2E STEPS PASSED ===")


async def _consume_until(ws, target_type: str, predicate, timeout: float = 5) -> dict:
    """Drain messages until predicate matches or timeout. Returns last message."""
    deadline = asyncio.get_event_loop().time() + timeout
    last = {}
    while asyncio.get_event_loop().time() < deadline:
        remaining = deadline - asyncio.get_event_loop().time()
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
        except asyncio.TimeoutError:
            return last
        msg = json.loads(raw)
        last = msg
        if predicate(msg):
            return msg
    return last


async def _wait_for(ws, msg_type: str, timeout: float = 5, **filters) -> dict:
    """Wait for a specific message type. Optionally filter by extra fields (e.g., kind)."""
    def predicate(m):
        if m.get("type") != msg_type:
            return False
        for k, v in filters.items():
            if m.get(k) != v:
                return False
        return True
    result = await _consume_until(ws, msg_type, predicate, timeout)
    if not predicate(result):
        raise RuntimeError(f"timeout waiting for {msg_type} {filters}; last={result}")
    return result


if __name__ == "__main__":
    asyncio.run(main())
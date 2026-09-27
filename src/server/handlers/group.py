# SPDX-License-Identifier: MIT
"""Group chat WS handler — routes group.* messages."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket

from src.memory.agent_members import AgentMemberStore
from src.memory.member_tokens import MemberTokenStore
from src.memory.rooms import RoomStore
from src.server.group_engine import UNKNOWN_SPEAKER, GroupEngine
from src.utils.logger import logger

_engine: GroupEngine | None = None
_rooms: RoomStore | None = None
_agent_members: AgentMemberStore | None = None
_member_tokens: MemberTokenStore | None = None
_tasks: dict[int, asyncio.Task[None]] = {}


def set_engine(
    engine: GroupEngine,
    rooms: RoomStore,
    agent_members: AgentMemberStore | None = None,
    member_tokens: MemberTokenStore | None = None,
) -> None:
    """Wired once from ws_server. The two stores are optional so the existing
    group tests can keep calling set_engine(engine, rooms); omitting them
    clears them, so one test's stores never leak into the next."""
    global _engine, _rooms, _agent_members, _member_tokens
    _engine = engine
    _rooms = rooms
    _agent_members = agent_members
    _member_tokens = member_tokens


def _agent_names(room_id: int) -> dict[str, str]:
    if _agent_members is None:
        return {}
    return {m.ref: m.display_name for m in _agent_members.members(room_id)}


def _room_payload(
    room: Any, rooms: RoomStore, agent_members: Any = None,
) -> dict[str, Any]:
    data = room.to_dict()
    data["members"] = rooms.members(room.id)
    store = _agent_members if agent_members is None else agent_members
    data["agent_members"] = (
        [
            {"ref": m.ref, "display_name": m.display_name, "state": m.state}
            for m in store.members(room.id)
        ]
        if store is not None
        else []
    )
    return data


def _start_chain(room_id: int, coro) -> None:
    previous = _tasks.get(room_id)
    if previous is not None and not previous.done():
        previous.cancel()
    task = asyncio.create_task(coro)
    _tasks[room_id] = task
    task.add_done_callback(
        lambda done: _tasks.pop(room_id, None) if _tasks.get(room_id) is done else None
    )


def _user_card(engine: GroupEngine, room: Any):
    repo = engine.chat.card_repo
    return (
        repo.get_user_card(room.user_card_id) if room.user_card_id else None
    ) or repo.get_default_user_card()


class _BroadcastSocket:
    """A stand-in websocket that fans events out to every live GUI socket.

    run_chain emits speaker deltas and chain.finished through whatever ws it
    was handed. An HTTP ingress has no socket, so it passes this instead of
    None — otherwise _safe_send would blow up mid-chain and the room would be
    left with chainRunning stuck on."""

    async def send_json(self, payload: dict[str, Any]) -> None:
        from src.server.handlers.chat import _broadcast

        await _broadcast(payload)


FREE_SPEECH_MAX_ROUNDS = 4
_MAX_MEMBER_TEXT = 16 * 1024


def _chain_cap_for(room: Any) -> int | None:
    """None means "use the room's own max_rounds".

    Rooms without agent members keep the companion behaviour exactly, including
    0 = unlimited.
    """
    if _agent_members is None:
        return None
    if int(getattr(room, "max_rounds", 0) or 0) != 0:
        return None
    if not _agent_members.members(room.id):
        return None
    return FREE_SPEECH_MAX_ROUNDS


async def post_member_message(
    *, room_id: int, member_ref: str, content: str, ws: Any = None,
) -> dict[str, Any]:
    """Record one external member's line and let the characters answer it.

    Shared by the WS type and the HTTP ingress, so the LAN phase only has to
    swap authentication, not this logic. Identity is never read from the
    content — the caller resolved it from the member's token.
    """
    engine = _engine
    rooms = _rooms
    if engine is None or rooms is None or _agent_members is None:
        return {"ok": False, "code": "not_ready", "row_id": None}
    text = content.strip()
    if not text:
        return {"ok": False, "code": "empty", "row_id": None}
    if len(text) > _MAX_MEMBER_TEXT:
        return {"ok": False, "code": "too_long", "row_id": None}
    member = _agent_members.get(room_id, member_ref)
    if member is None:
        return {"ok": False, "code": "no_member", "row_id": None}
    if member.state != "active":
        return {"ok": False, "code": "muted", "row_id": None}
    room = rooms.get(room_id)
    if room is None:
        return {"ok": False, "code": "no_room", "row_id": None}

    chat = engine.chat
    row_id = await asyncio.to_thread(
        chat.session_store.append_message,
        room.session_id, "assistant", text,
        speaker_kind="agent", speaker_ref=member_ref,
    )
    sock = ws or _BroadcastSocket()
    await sock.send_json({
        "type": "group.user_message",
        "room_id": room_id,
        "message_id": str(row_id) if row_id is not None else None,
        "row_id": row_id,
        "content": text,
        "speaker_kind": "agent",
        "member_ref": member_ref,
        "user_name": member.display_name,
    })
    override = _chain_cap_for(room)
    _start_chain(room_id, engine.run_chain(
        sock, room=room, user_input=text, mentioned=[],
        user_card=_user_card(engine, room), max_rounds_override=override,
    ))
    return {"ok": True, "code": "ok", "row_id": row_id}


async def dispatch(ws: WebSocket, msg: dict[str, Any]) -> bool:
    t = msg.get("type")
    if _engine is None or _rooms is None or not t.startswith("group."):
        return False

    rooms = _rooms
    engine = _engine
    try:
        if t == "group.list":
            rooms.prune_missing_members()
            await ws.send_json({
                "type": "group.list.ok",
                "rooms": [_room_payload(r, rooms) for r in rooms.list()],
            })
            return True

        if t == "group.create":
            name = str(msg.get("name", "")).strip()
            if not name:
                await ws.send_json({
                    "type": "group.error", "code": "invalid_name",
                    "message": "A room needs a name.",
                })
                return True
            character_ids = [int(c) for c in (msg.get("character_ids") or [])]
            if not character_ids:
                await ws.send_json({
                    "type": "group.error", "code": "no_members",
                    "message": "Pick at least one character.",
                })
                return True
            room = await asyncio.to_thread(
                rooms.create,
                name=name,
                description=str(msg.get("description", "") or ""),
                scenario_prompt=str(msg.get("scenario_prompt", "") or ""),
                user_card_id=(
                    int(msg["user_card_id"]) if msg.get("user_card_id") else None
                ),
                character_ids=character_ids,
                max_rounds=int(msg.get("max_rounds") or 0),
                agent_mode=bool(msg.get("agent_mode")),
                lan_enabled=bool(msg.get("lan_enabled")),
            )
            await ws.send_json({
                "type": "group.created",
                "room": _room_payload(room, rooms),
            })
            return True

        if t == "group.update":
            room = rooms.update(
                int(msg["room_id"]),
                name=(
                    str(msg["name"]).strip() if msg.get("name") is not None else None
                ),
                description=msg.get("description"),
                scenario_prompt=msg.get("scenario_prompt"),
                user_card_id=msg.get("user_card_id"),
                pinned=msg.get("pinned"),
                max_rounds=(
                    int(msg["max_rounds"]) if msg.get("max_rounds") is not None
                    else None
                ),
                agent_mode=msg.get("agent_mode"),
                lan_enabled=msg.get("lan_enabled"),
            )
            if room is not None:
                await ws.send_json({
                    "type": "group.updated",
                    "room": _room_payload(room, rooms),
                })
            return True

        if t == "group.delete":
            room_id = int(msg["room_id"])
            engine.cancel(room_id)
            task = _tasks.pop(room_id, None)
            if task is not None and not task.done():
                task.cancel()
            rooms.delete(room_id)
            await ws.send_json({"type": "group.deleted", "room_id": room_id})
            return True

        if t == "group.members.add":
            room_id = int(msg["room_id"])
            rooms.add_members(
                room_id, [int(c) for c in (msg.get("character_ids") or [])],
            )
            room = rooms.get(room_id)
            if room is not None:
                await ws.send_json({
                    "type": "group.updated",
                    "room": _room_payload(room, rooms),
                })
            return True

        if t == "group.members.remove":
            room_id = int(msg["room_id"])
            rooms.remove_member(room_id, int(msg["character_id"]))
            room = rooms.get(room_id)
            if room is not None:
                await ws.send_json({
                    "type": "group.updated",
                    "room": _room_payload(room, rooms),
                })
            return True

        if t == "group.history":
            room_id = int(msg["room_id"])
            room = rooms.get(room_id)
            if room is None:
                return True
            names: dict[int, str] = {}
            for cid in rooms.members(room_id):
                character = engine.chat.card_repo.get_character(cid)
                if character is not None:
                    names[cid] = getattr(character, "name", "") or ""
            agent_names = _agent_names(room_id)
            card = _user_card(engine, room)
            user_name = getattr(card, "name", "") or "user"
            messages = [
                {
                    "id": str(r.id),
                    "row_id": r.id,
                    "role": r.role,
                    "content": r.content,
                    "character_id": r.character_card_id,
                    "character_name": (
                        agent_names.get(r.speaker_ref or "", UNKNOWN_SPEAKER)
                        if getattr(r, "speaker_kind", None) == "agent"
                        else (
                            names.get(r.character_card_id)
                            if r.character_card_id else None
                        )
                    ),
                    "speaker_kind": getattr(r, "speaker_kind", None),
                    "user_name": user_name if r.role == "user" else None,
                    "timestamp": r.timestamp.isoformat(),
                }
                for r in rooms.messages_with_speaker(room_id)
            ]
            await ws.send_json({
                "type": "group.history.ok",
                "room_id": room_id,
                "messages": messages,
            })
            return True

        if t == "group.cancel":
            engine.cancel(int(msg["room_id"]))
            return True

        if t == "group.rate":
            room_id = int(msg["room_id"])
            room = rooms.get(room_id)
            if room is None:
                return True
            result = engine.chat.rate(
                str(msg.get("message_id", "")),
                int(msg.get("score", 0)),
                str(msg.get("reason", "") or ""),
                session_id=room.session_id,
            )
            await ws.send_json({
                "type": "group.rate.ack",
                "room_id": room_id,
                "message_id": msg.get("message_id"),
                **result,
            })
            return True

        if t == "group.send":
            room_id = int(msg["room_id"])
            room = rooms.get(room_id)
            if room is None:
                return True
            if not rooms.members(room_id):
                await ws.send_json({
                    "type": "group.error", "room_id": room_id,
                    "code": "no_members",
                    "message": "This room has no characters.",
                })
                return True
            content = str(msg.get("content", ""))
            files = [str(f) for f in (msg.get("attached_files") or [])]
            chat = engine.chat
            marker, block = chat._render_attachments(files) if files else ("", "")
            stored = f"{content}{marker}"
            llm_content = f"{stored}\n\n{block}" if block else stored
            await asyncio.to_thread(chat.note_arrival, room.session_id)
            row_id = await asyncio.to_thread(
                chat.session_store.append_message,
                room.session_id, "user", stored,
            )
            mentioned = [int(c) for c in (msg.get("mentioned_character_ids") or [])]
            card = _user_card(engine, room)
            # Echo the stored message back: without this the user's own line only
            # appeared after a reload, because history is the only other source.
            await ws.send_json({
                "type": "group.user_message",
                "room_id": room_id,
                "message_id": str(row_id) if row_id is not None else None,
                "row_id": row_id,
                "content": stored,
                "user_name": getattr(card, "name", "") or "user",
            })
            _start_chain(room_id, engine.run_chain(
                ws, room=room, user_input=llm_content,
                mentioned=mentioned, user_card=card,
                max_rounds_override=_chain_cap_for(room),
            ))
            return True

        if t == "group.member.say":
            result = await post_member_message(
                room_id=int(msg["room_id"]),
                member_ref=str(msg.get("member_ref", "")),
                content=str(msg.get("content", "")),
                ws=ws,
            )
            if not result["ok"]:
                await ws.send_json({
                    "type": "group.error", "room_id": msg.get("room_id"),
                    "code": result["code"],
                    "message": "Member message rejected.",
                })
            return True

        if t == "group.agent.mute":
            room_id = int(msg["room_id"])
            ref = str(msg.get("member_ref", ""))
            if _agent_members is None or _agent_members.get(room_id, ref) is None:
                await ws.send_json({
                    "type": "group.error", "room_id": room_id,
                    "code": "no_member", "message": "Unknown agent member.",
                })
                return True
            state = "muted" if msg.get("muted") else "active"
            await asyncio.to_thread(_agent_members.set_state, room_id, ref, state)
            room = rooms.get(room_id)
            if room is not None:
                await ws.send_json({
                    "type": "group.updated",
                    "room": _room_payload(room, rooms, _agent_members),
                })
            return True

        if t == "group.agent.remove":
            room_id = int(msg["room_id"])
            ref = str(msg.get("member_ref", ""))
            if _agent_members is None or _agent_members.get(room_id, ref) is None:
                await ws.send_json({
                    "type": "group.error", "room_id": room_id,
                    "code": "no_member", "message": "Unknown agent member.",
                })
                return True
            await asyncio.to_thread(_agent_members.remove, room_id, ref)
            # Two locks together: dropping the membership already makes the
            # ingress refuse the member, but a live token would still show up
            # as valid in the panel.
            if _member_tokens is not None:
                for row in await asyncio.to_thread(
                    _member_tokens.list_for, room_id, ref,
                ):
                    await asyncio.to_thread(_member_tokens.revoke, int(row["id"]))
            room = rooms.get(room_id)
            if room is not None:
                await ws.send_json({
                    "type": "group.updated",
                    "room": _room_payload(room, rooms, _agent_members),
                })
            return True

        if t == "group.stop_all":
            for room_id in list(_tasks):
                engine.cancel(room_id)
            await ws.send_json({"type": "group.stop_all.ack"})
            return True

        if t == "group.regenerate":
            room_id = int(msg["room_id"])
            room = rooms.get(room_id)
            if room is None:
                return True
            card = _user_card(engine, room)
            # Detached like group.send: awaiting it here would block the
            # receive loop for the whole stream, so group.cancel could not
            # interrupt a regenerate.
            _start_chain(room_id, engine.regenerate(
                ws, room=room,
                message_row_id=int(msg["message_id"]), user_card=card,
            ))
            return True
    except Exception as e:
        logger.warning(f"{t} failed: {e}")
        try:
            await ws.send_json({
                "type": "group.error",
                "room_id": msg.get("room_id"),
                "code": "group_handler",
                "message": str(e),
            })
        except Exception:
            pass
        return True

    return False

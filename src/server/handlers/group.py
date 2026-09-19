# SPDX-License-Identifier: MIT
"""Group chat WS handler — routes group.* messages."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket

from src.memory.rooms import RoomStore
from src.server.group_engine import GroupEngine
from src.utils.logger import logger

_engine: GroupEngine | None = None
_rooms: RoomStore | None = None
_tasks: dict[int, asyncio.Task[None]] = {}


def set_engine(engine: GroupEngine, rooms: RoomStore) -> None:
    global _engine, _rooms
    _engine = engine
    _rooms = rooms


def _room_payload(room: Any, rooms: RoomStore) -> dict[str, Any]:
    data = room.to_dict()
    data["members"] = rooms.members(room.id)
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
                        names.get(r.character_card_id)
                        if r.character_card_id else None
                    ),
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
            ))
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

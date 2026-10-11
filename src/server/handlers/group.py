# SPDX-License-Identifier: MIT
"""Group chat WS handler — routes group.* messages."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import WebSocket

from src.memory.agent_members import AgentMemberStore
from src.memory.member_tokens import MemberTokenStore
from src.memory.rooms import RoomStore
from src.server.group_engine import UNKNOWN_SPEAKER, GroupEngine
from src.server.patch_landing import land_patch
from src.server.publish_export import ExportError, build_export
from src.utils.logger import logger

_engine: GroupEngine | None = None
_rooms: RoomStore | None = None
_agent_members: AgentMemberStore | None = None
_member_tokens: MemberTokenStore | None = None
_lan_supervisor: Any = None
_room_plans: Any = None
_room_runner: Any = None
_room_publishes: Any = None
_room_patches: Any = None
_room_workspaces: Any = None
_room_project_root: Any = None
_tasks: dict[int, asyncio.Task[None]] = {}


def _stored_tool_steps(row: Any) -> list[dict]:
    """The tool calls a stored turn made.

    The arguments go out as they were recorded, so the client renders them
    with the same helper its live events use. No result is stored, so none is
    sent.
    """
    raw = getattr(row, "tool_steps", "") or ""
    if not raw:
        return []
    try:
        steps = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(steps, list):
        return []
    return [s for s in steps if isinstance(s, dict)]


def set_lan_supervisor(supervisor: Any) -> None:
    global _lan_supervisor
    _lan_supervisor = supervisor


def set_room_plan_engine(rooms: Any, plans: Any) -> None:
    """Wired once from ws_server alongside set_engine."""
    global _rooms, _room_plans
    _rooms = rooms
    _room_plans = plans


def set_room_publish(publishes: Any, project_root_for: Any) -> None:
    global _room_publishes, _room_project_root
    _room_publishes = publishes
    _room_project_root = project_root_for


def set_room_patch(patches: Any, workspaces: Any) -> None:
    global _room_patches, _room_workspaces
    _room_patches = patches
    _room_workspaces = workspaces


def set_room_runner(runner: Any) -> None:
    global _room_runner
    _room_runner = runner


def _sync_lan() -> None:
    """The listener follows the room switches. Best effort — the periodic tick
    in ws_server is the safety net for a missed call here."""
    if _lan_supervisor is None:
        return
    try:
        _lan_supervisor.sync()
    except Exception as e:
        logger.warning(f"lan sync failed: {e}")


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


def _agent_list_payload(room_id: int) -> dict[str, Any]:
    """Every agent member plus its token metadata — never a token secret."""
    return {
        "agents": [
            {
                "ref": m.ref,
                "display_name": m.display_name,
                "state": m.state,
                "tokens": (
                    _member_tokens.list_for(room_id, m.ref)
                    if _member_tokens is not None
                    else []
                ),
            }
            for m in (_agent_members.members(room_id) if _agent_members else [])
        ],
    }


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
    if t.startswith("room."):
        if _rooms is None or _room_plans is None:
            return False
        await _handle_room_message(ws, msg)
        return True
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
                sandbox_workspace_id=(
                    int(msg["sandbox_workspace_id"])
                    if msg.get("sandbox_workspace_id") is not None else None
                ),
            )
            _sync_lan()
            await ws.send_json({
                "type": "group.created",
                "room": _room_payload(room, rooms),
            })
            return True

        if t == "group.update":
            if msg.get("agent_mode") is not None:
                # The mode decides which route the room's characters run on, so
                # it is chosen when the room is made. LAN is the opposite: a
                # network fact the owner changes without rebuilding the room.
                await ws.send_json({
                    "type": "group.error",
                    "room_id": int(msg.get("room_id") or 0),
                    "code": "mode_not_editable",
                    "message": "Agent mode is fixed when the room is created.",
                })
                return True
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
                lan_enabled=msg.get("lan_enabled"),
            )
            if room is not None and "sandbox_workspace_id" in msg:
                # Its own door: update() reads None as leave-alone, so clearing
                # the sandbox would otherwise be impossible to ask for.
                room = rooms.set_sandbox(
                    int(msg["room_id"]), msg.get("sandbox_workspace_id"),
                )
            if room is not None:
                _sync_lan()
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
            _sync_lan()
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
                    "tools": _stored_tool_steps(r),
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

        if t == "group.agent.add":
            room_id = int(msg["room_id"])
            ref = str(msg.get("ref", "")).strip()
            display = str(msg.get("display_name", "")).strip() or ref
            if not ref:
                await ws.send_json({
                    "type": "group.error", "room_id": room_id,
                    "code": "bad_ref", "message": "Member ref must not be empty.",
                })
                return True
            if _agent_members is None:
                return True
            try:
                await asyncio.to_thread(
                    _agent_members.add, room_id, ref=ref, display_name=display,
                )
            except Exception:
                await ws.send_json({
                    "type": "group.error", "room_id": room_id,
                    "code": "duplicate_ref",
                    "message": "That member ref is already in this room.",
                })
                return True
            room = rooms.get(room_id)
            if room is not None:
                await ws.send_json({
                    "type": "group.updated",
                    "room": _room_payload(room, rooms, _agent_members),
                })
            return True

        if t == "group.agent.list":
            room_id = int(msg["room_id"])
            await ws.send_json({
                "type": "group.agent.list.ok", "room_id": room_id,
                **_agent_list_payload(room_id),
            })
            return True

        if t == "group.agent.token.issue":
            room_id = int(msg["room_id"])
            ref = str(msg.get("member_ref", ""))
            if _agent_members is None or _agent_members.get(room_id, ref) is None:
                await ws.send_json({
                    "type": "group.error", "room_id": room_id,
                    "code": "no_member", "message": "Unknown agent member.",
                })
                return True
            issued = await asyncio.to_thread(
                _member_tokens.issue, room_id, ref,
                label=str(msg.get("label", "")),
            )
            # The only place a member token is ever sent in the clear. The GUI
            # shows it once; it is never stored or logged.
            await ws.send_json({
                "type": "group.agent.token.issued",
                "room_id": room_id,
                "member_ref": ref,
                "token_id": issued.token_id,
                "token": issued.token,
            })
            return True

        if t == "group.agent.token.revoke":
            room_id = int(msg["room_id"])
            await asyncio.to_thread(
                _member_tokens.revoke, int(msg["token_id"]),
            )
            await ws.send_json({
                "type": "group.agent.list.ok", "room_id": room_id,
                **_agent_list_payload(room_id),
            })
            return True

        if t == "group.agent.token.unban":
            room_id = int(msg["room_id"])
            await asyncio.to_thread(
                _member_tokens.unban, int(msg["token_id"]),
            )
            await ws.send_json({
                "type": "group.agent.list.ok", "room_id": room_id,
                **_agent_list_payload(room_id),
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


async def _handle_room_message(ws: WebSocket, msg: dict[str, Any]) -> None:
    """The room's own messages: a goal, the board, the phase.

    Room messages never execute anything and are not offered to members — the
    LAN app does not register them at all.
    """
    room_id = int(msg.get("room_id") or 0)
    try:
        room = await asyncio.to_thread(_rooms.get, room_id)
        if room is None:
            await ws.send_json({
                "type": "group.error", "room_id": room_id,
                "code": "not_found", "message": "No such room.",
            })
            return
        if not getattr(room, "agent_mode", False):
            await ws.send_json({
                "type": "group.error", "room_id": room_id,
                "code": "not_agent_room",
                "message": "That room is not in agent mode.",
            })
            return

        msg_type = str(msg.get("type"))
        if msg_type == "room.goal.set":
            await _set_goal(ws, room, str(msg.get("goal") or ""))
        elif msg_type == "room.plan.list":
            await _push_plan(ws, room)
        elif msg_type == "room.plan.tick":
            if _room_runner is not None:
                await _room_runner.tick(room)
            await _push_plan(ws, room)
        elif msg_type == "room.phase.confirm_done":
            await _confirm_done(ws, room)
        elif msg_type == "room.plan.unbind":
            await _unbind_workspace(ws, room)
        elif msg_type == "room.publish.request":
            await _request_publish(ws, room, msg.get("allowlist"))
        elif msg_type == "room.publish.list":
            await _push_publishes(ws, room)
        elif msg_type == "room.patch.list":
            await _push_patches(ws, room)
        elif msg_type == "room.patch.text":
            await _send_patch_text(ws, room, msg.get("patch_id"))
        elif msg_type == "room.patch.decide":
            await _decide_patch(
                ws, room, msg.get("patch_id"), bool(msg.get("approve")),
            )
    except Exception as e:
        logger.warning(f"room handler failed: {e}")
        await ws.send_json({
            "type": "group.error", "room_id": room_id,
            "code": "group_handler", "message": "The room action failed.",
        })


async def _push_plan(ws: WebSocket, room: Any) -> None:
    items = await asyncio.to_thread(_room_plans.list, room.id)
    await ws.send_json({
        "type": "room.plan.updated",
        "room_id": room.id,
        "items": [i.to_dict() for i in items],
    })


async def _push_publishes(ws: WebSocket, room: Any) -> None:
    records = await asyncio.to_thread(_room_publishes.list, room.id)
    await ws.send_json({
        "type": "room.publish.updated", "room_id": room.id,
        "publishes": [r.to_dict() for r in records],
    })


async def _request_publish(ws: WebSocket, room: Any, allowlist: Any) -> None:
    """The owner packages a snapshot for the members to work from.

    Nothing is sent anywhere by this call and nothing is executed: the package
    is written to disk, and a member fetches it with its own credential.
    """
    if _room_publishes is None or _room_project_root is None:
        return
    root = await asyncio.to_thread(_room_project_root, room)
    if not root:
        await ws.send_json({
            "type": "group.error", "room_id": room.id, "code": "no_project",
            "message": "This room has no project bound.",
        })
        return
    patterns = [str(p) for p in (allowlist or []) if str(p).strip()]
    try:
        result = await asyncio.to_thread(build_export, root, patterns, room.id)
    except ExportError as exc:
        await ws.send_json({
            "type": "group.error", "room_id": room.id,
            "code": exc.code, "message": str(exc),
        })
        return
    await asyncio.to_thread(
        _room_publishes.record, room.id, "owner",
        path_count=result.path_count, byte_count=result.byte_count,
        digest=result.digest,
    )
    await _push_publishes(ws, room)
    await ws.send_json({
        "type": "room.publish.ready", "room_id": room.id,
        "path_count": result.path_count, "bytes": result.byte_count,
    })


async def _push_patches(ws: WebSocket, room: Any) -> None:
    records = await asyncio.to_thread(_room_patches.list, room.id)
    await ws.send_json({
        "type": "room.patch.updated", "room_id": room.id,
        "patches": [p.to_dict() for p in records],
    })


async def _send_patch_text(ws: WebSocket, room: Any, patch_id: Any) -> None:
    """The text on demand: a queue listing does not carry it."""
    if _room_patches is None:
        return
    text = await asyncio.to_thread(_room_patches.text, room.id, int(patch_id or 0))
    if text is None:
        await ws.send_json({
            "type": "group.error", "room_id": room.id, "code": "not_found",
            "message": "No such patch.",
        })
        return
    await ws.send_json({
        "type": "room.patch.text", "room_id": room.id,
        "patch_id": int(patch_id or 0), "patch": text,
    })


async def _decide_patch(
    ws: WebSocket, room: Any, patch_id: Any, approve: bool,
) -> None:
    """Landed or refused, once. The patch is applied as text and judged on the
    tree it produced — nothing about it is executed."""
    if (
        _room_patches is None or _room_workspaces is None
        or _room_project_root is None
    ):
        return
    pid = int(patch_id or 0)
    patch = await asyncio.to_thread(_room_patches.get, room.id, pid)
    if patch is None or patch.state != "pending":
        await ws.send_json({
            "type": "group.error", "room_id": room.id, "code": "not_pending",
            "message": "That patch is not waiting.",
        })
        return

    if not approve:
        await asyncio.to_thread(
            _room_patches.decide, room.id, pid, "rejected",
            reason="refused by the owner", decided_by="user",
        )
        await _finish_patch(ws, room, pid, "rejected", "", "")
        return

    root = await asyncio.to_thread(_room_project_root, room)
    if not root:
        await ws.send_json({
            "type": "group.error", "room_id": room.id, "code": "no_project",
            "message": "This room has no project bound.",
        })
        return

    text = await asyncio.to_thread(_room_patches.text, room.id, pid)
    landed, reason, sha = await asyncio.to_thread(
        land_patch, project_root=root, workspaces=_room_workspaces, room=room,
        member_ref=patch.member_ref, patch_text=text or "", item_key=patch.item_key,
    )
    state = "landed" if landed else "rejected"
    await asyncio.to_thread(
        _room_patches.decide, room.id, pid, state,
        reason=reason, decided_by="user",
    )
    if landed and patch.item_key:
        await asyncio.to_thread(
            _room_patches.supersede_pending, room.id, patch.item_key,
        )
        await _mark_landed(room, patch.item_key, sha)
    await _finish_patch(ws, room, pid, state, reason, sha if landed else "")


async def _mark_landed(room: Any, item_key: str, sha: str) -> None:
    """A patch that answers a plan item settles that item too; otherwise the
    board would keep asking for work that has already come back."""
    item = await asyncio.to_thread(_room_plans.get, room.id, item_key)
    if item is None:
        return
    await asyncio.to_thread(_room_plans.set_commit_ref, room.id, item_key, sha)
    await asyncio.to_thread(
        _room_plans.set_status, room.id, item_key, "done",
        evidence=f"landed {sha[:12]}",
    )


async def _finish_patch(
    ws: WebSocket, room: Any, patch_id: int, state: str, reason: str,
    commit_ref: str,
) -> None:
    await _push_patches(ws, room)
    await _push_plan(ws, room)
    await ws.send_json({
        "type": "room.patch.decided", "room_id": room.id,
        "patch_id": patch_id, "state": state, "reason": reason,
        "commit_ref": commit_ref,
    })


async def _set_goal(ws: WebSocket, room: Any, goal: str) -> None:
    """Setting a goal is the room's only manual start: it enters planning and
    gives the characters one round to turn the goal into plan items."""
    room = await asyncio.to_thread(
        _rooms.update, room.id, goal=goal, phase="planning",
    )
    await ws.send_json({
        "type": "room.phase.changed", "room_id": room.id,
        "phase": "planning", "reason": "goal_set",
    })
    await _push_plan(ws, room)
    if _engine is not None and goal.strip():
        _start_chain(room.id, _engine.run_chain(
            _BroadcastSocket(), room=room, user_input=goal, mentioned=[],
            user_card=_user_card(_engine, room),
        ))


async def _confirm_done(ws: WebSocket, room: Any) -> None:
    await asyncio.to_thread(_rooms.update, room.id, phase="done")
    await ws.send_json({
        "type": "room.phase.changed", "room_id": room.id,
        "phase": "done", "reason": "user_confirmed",
    })


async def _unbind_workspace(ws: WebSocket, room: Any) -> None:
    """RoomStore.update treats None as 'leave alone', so unbinding needs its
    own door — otherwise a caller that simply forgets the argument would
    silently clear the binding."""
    await asyncio.to_thread(_rooms.clear_workspace, room.id)
    await ws.send_json({
        "type": "room.updated", "room_id": room.id, "workspace_id": None,
    })

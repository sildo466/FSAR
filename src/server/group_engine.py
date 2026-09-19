# SPDX-License-Identifier: MIT
"""Group chat orchestration: election, chained turns, cancellation."""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from src.core.prompts import build_character_prompt
from src.memory.session_store import MessageRow

if TYPE_CHECKING:
    from src.memory.rooms import RoomStore
    from src.server.chat_engine import ChatEngine


UNKNOWN_SPEAKER = "Unknown"

MAX_CHAIN_ROUNDS = 4
MAX_CHAIN_CALLS = 24
EAGER_THRESHOLD = 5
SPEAKERS_PER_ROUND = 2
MENTIONED_EAGERNESS = 10
ELECT_HISTORY_LINES = 20

ELECT_PROMPT = """Your name is {name}.
{description}
{personality}
{room_scene}
What has just been said in the group chat:
{history}
Decide how much you want to speak next, in character.
Return ONLY this JSON, nothing else:
{{"eagerness": <integer 0-10>, "reason": "<one short sentence>"}}
0-2: you have nothing to add. 3-5: you could say something. 6-10: you want to speak now."""

_EAGERNESS_RE = re.compile(r'\{[^{}]*"eagerness"[^{}]*\}', re.DOTALL)


def format_group_history(
    messages: list[MessageRow],
    *,
    names_by_id: dict[int, str],
    user_name: str,
) -> list[dict[str, str]]:
    """Prefix every message with its speaker.

    Every character message shares role="assistant", so without a prefix the
    model cannot tell who said what."""
    out: list[dict[str, str]] = []
    for row in messages:
        if row.role == "user":
            speaker = user_name or "user"
        else:
            speaker = names_by_id.get(row.character_card_id or -1, UNKNOWN_SPEAKER)
        out.append({
            "role": row.role,
            "content": f"[{speaker}]: {row.content}",
        })
    return out


def parse_eagerness(raw: str) -> tuple[int, str]:
    """Extract (eagerness, reason) from an election reply.

    Locates the JSON object by regex so markdown fences and surrounding prose
    are tolerated. Any failure yields (0, "") — a character that cannot answer
    simply stays silent this round."""
    if not raw:
        return 0, ""
    match = _EAGERNESS_RE.search(raw)
    if match is None:
        return 0, ""
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return 0, ""
    try:
        score = int(data.get("eagerness", 0))
    except (TypeError, ValueError):
        return 0, ""
    reason = str(data.get("reason", "") or "").strip()[:200]
    return max(0, min(10, score)), reason


@dataclass
class ElectResult:
    character_id: int
    character_name: str
    eagerness: int
    reason: str


def _one_completion(client: Any, provider_id: str, model: str, prompt: str) -> str:
    from src.utils.llm_factory import chat_completion
    result = chat_completion(
        client,
        provider_id=provider_id,
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=100000,
        stream=False,
    )
    try:
        return result.choices[0].message.content or ""
    except (AttributeError, IndexError):
        return ""


async def run_batch_completions(
    client: Any, *, provider_id: str, model: str, prompts: list[str],
) -> list[str]:
    """Run independent non-streaming completions concurrently.

    Returns one string per prompt; a failed call yields "" so the remaining
    members are unaffected."""

    async def one(prompt: str) -> str:
        try:
            return await asyncio.to_thread(
                _one_completion, client, provider_id, model, prompt,
            )
        except Exception:
            return ""

    return list(await asyncio.gather(*(one(p) for p in prompts)))


class _DeltaRelay:
    """Translates chat.* stream events into group.* and never lets a dead
    socket abort the turn."""

    def __init__(self, inner: Any, room_id: int) -> None:
        self._inner = inner
        self._room_id = room_id

    async def send_json(self, payload: dict) -> None:
        kind = payload.get("type")
        if kind == "chat.delta":
            out = {
                "type": "group.speaker.delta",
                "room_id": self._room_id,
                "message_id": payload["message_id"],
                "content": payload["content"],
            }
        elif kind == "chat.thinking":
            out = {
                "type": "group.speaker.thinking",
                "room_id": self._room_id,
                "message_id": payload["message_id"],
                "content": payload["content"],
            }
        else:
            return
        try:
            await self._inner.send_json(out)
        except Exception:
            pass


class GroupEngine:
    """Group chat orchestration. Reuses ChatEngine subsystems and owns nothing
    beyond per-room cancellation."""

    def __init__(self, chat: "ChatEngine", rooms: "RoomStore") -> None:
        self.chat = chat
        self.rooms = rooms
        self._cancelled: set[int] = set()

    async def _safe_send(self, ws: Any, payload: dict[str, Any]) -> None:
        try:
            await ws.send_json(payload)
        except Exception:
            pass

    def cancel(self, room_id: int) -> None:
        self._cancelled.add(room_id)

    def is_cancelled(self, room_id: int) -> bool:
        return room_id in self._cancelled

    def clear_cancel(self, room_id: int) -> None:
        self._cancelled.discard(room_id)

    async def speak(
        self,
        ws: Any,
        *,
        room: Any,
        character: Any,
        user_card: Any,
        history: list[dict[str, str]],
        user_input: str,
        should_stop: Any,
    ) -> tuple[str, str]:
        """One character's turn: in-character prompt, one streaming call.

        Returns (message_id, text). Memory cleansing is deliberately skipped —
        it costs an extra model call per speaker per round."""
        chat = self.chat
        conv_id = room.session_id
        message_id = f"group_{uuid.uuid4().hex[:12]}"
        char_id = getattr(character, "id", None)
        char_name = getattr(character, "name", None)
        await self._safe_send(ws, {
            "type": "group.speaker.start",
            "room_id": room.id,
            "message_id": message_id,
            "character_id": char_id,
            "character_name": char_name,
        })

        memory_block = await asyncio.to_thread(
            chat._memory_block, user_input, character=character,
        )
        system_prompt = build_character_prompt(
            character=character,
            user_card=user_card,
            memory_block=memory_block,
            room_scene=getattr(room, "scenario_prompt", ""),
            tools_enabled=False,
        )
        client, model, provider_id = chat.client_and_model()
        _, max_output = chat._model_limits()
        messages: list[Any] = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        if user_input:
            messages.append({"role": "user", "content": user_input})

        text = await chat._stream_one_reply(
            _DeltaRelay(ws, room.id),
            message_id=message_id,
            conv_id=conv_id,
            client=client,
            model=model,
            provider_id=provider_id,
            provider_family=chat._active_provider_family(),
            messages=messages,
            max_output=max_output,
            model_effort=chat._model_thinking_effort(),
            should_stop=should_stop,
            character=character,
            char_name=char_name,
        )
        chat._save_assistant(message_id, conv_id, text, character_id=char_id)
        emotion_state = None
        try:
            emotion_state = chat._post_turn_emotion_pass(conv_id, char_id=char_id)
        except Exception:
            emotion_state = None
        try:
            await chat._maybe_queue_tts(
                ws,
                message_id=message_id,
                text=text,
                conversation_id=conv_id,
                character_id=char_id,
            )
        except Exception:
            pass
        await self._safe_send(ws, {
            "type": "group.speaker.done",
            "room_id": room.id,
            "message_id": message_id,
            "emotion_state": emotion_state,
        })
        return message_id, text

    def _elect_prompt(
        self, character: Any, *, room_scene: str, history_text: str,
    ) -> str:
        scene = (room_scene or "").strip()
        return ELECT_PROMPT.format(
            name=getattr(character, "name", "") or "Unknown",
            description=getattr(character, "description", "") or "",
            personality=getattr(character, "personality", "") or "",
            room_scene=f"Scene: {scene}" if scene else "",
            history=history_text or "(nothing yet)",
        )

    async def elect(
        self,
        ws: Any,
        *,
        room: Any,
        candidates: list[Any],
        history_block: list[dict[str, str]],
        mentioned: list[int],
        chain_id: str,
        round_no: int,
    ) -> list[ElectResult]:
        """Run one election round. All candidates are queried concurrently."""
        if not candidates:
            return []
        history_text = "\n".join(
            m["content"] for m in history_block[-ELECT_HISTORY_LINES:]
        )
        prompts = [
            self._elect_prompt(
                c,
                room_scene=getattr(room, "scenario_prompt", ""),
                history_text=history_text,
            )
            for c in candidates
        ]
        await self._safe_send(ws, {
            "type": "group.elect.started",
            "room_id": room.id,
            "chain_id": chain_id,
            "round": round_no,
            "candidates": [getattr(c, "id", None) for c in candidates],
        })
        client, model, provider_id = self.chat.client_and_model()
        raws = await run_batch_completions(
            client, provider_id=provider_id, model=model, prompts=prompts,
        )
        results: list[ElectResult] = []
        for character, raw in zip(candidates, raws):
            score, reason = parse_eagerness(raw)
            char_id = getattr(character, "id", None)
            char_name = getattr(character, "name", "") or ""
            if char_id in mentioned:
                score, reason = MENTIONED_EAGERNESS, "mentioned"
            results.append(ElectResult(
                character_id=char_id,
                character_name=char_name,
                eagerness=score,
                reason=reason,
            ))
            await self._safe_send(ws, {
                "type": "group.elect.candidate",
                "room_id": room.id,
                "chain_id": chain_id,
                "round": round_no,
                "character_id": char_id,
                "character_name": char_name,
                "eagerness": score,
                "reason": reason,
            })
        results.sort(key=lambda r: r.eagerness, reverse=True)
        return results

    def _speaker_names(self, room: Any) -> tuple[dict[int, str], str]:
        chat = self.chat
        names: dict[int, str] = {}
        for cid in self.rooms.members(room.id):
            character = chat.card_repo.get_character(cid)
            if character is not None:
                names[cid] = getattr(character, "name", "") or ""
        user_card_id = getattr(room, "user_card_id", None)
        card = (
            chat.card_repo.get_user_card(user_card_id) if user_card_id else None
        ) or chat.card_repo.get_default_user_card()
        return names, getattr(card, "name", "") or "user"

    def _history_block(self, room: Any) -> list[dict[str, str]]:
        names, user_name = self._speaker_names(room)
        rows = self.chat.session_store.get_session_messages(room.session_id)
        return format_group_history(rows, names_by_id=names, user_name=user_name)

    def _trigger_for(
        self, room: Any, first_input: str | None,
    ) -> tuple[list[dict[str, str]], str]:
        """History for the next speaker plus the message that triggered them.

        The trigger is kept out of history so nobody sees it twice. The first
        turn uses the caller's text because it may carry attachment bodies that
        are not persisted; later turns read the room back."""
        block = self._history_block(room)
        if first_input is not None:
            if block and block[-1]["role"] == "user":
                block = block[:-1]
            return block, first_input
        if not block:
            return [], ""
        return block[:-1], block[-1]["content"]

    async def run_chain(
        self,
        ws: Any,
        *,
        room: Any,
        user_input: str,
        mentioned: list[int],
        user_card: Any,
    ) -> str:
        """Chain rounds until nobody is eager enough or a hard cap is hit."""
        chat = self.chat
        chain_id = f"chain_{uuid.uuid4().hex[:12]}"
        members = [
            chat.card_repo.get_character(cid)
            for cid in self.rooms.members(room.id)
        ]
        members = [c for c in members if c is not None]
        self.clear_cancel(room.id)
        if not members:
            await self._safe_send(ws, {
                "type": "group.error",
                "room_id": room.id,
                "code": "no_members",
                "message": "This room has no characters.",
            })
            return "settled"

        calls_used = 0
        last_speaker: int | None = None
        first_speaker = True
        reason = "settled"

        for round_no in range(1, MAX_CHAIN_ROUNDS + 1):
            if MAX_CHAIN_CALLS - calls_used < len(members) + 1:
                reason = "max_calls"
                break
            results = await self.elect(
                ws,
                room=room,
                candidates=members,
                history_block=self._history_block(room),
                mentioned=mentioned if round_no == 1 else [],
                chain_id=chain_id,
                round_no=round_no,
            )
            calls_used += len(members)
            eager = [r for r in results if r.eagerness >= EAGER_THRESHOLD]
            if not eager:
                break
            chosen = [
                r for r in eager if r.character_id != last_speaker
            ][:SPEAKERS_PER_ROUND]
            if not chosen:
                break
            await self._safe_send(ws, {
                "type": "group.elect.decided",
                "room_id": room.id,
                "chain_id": chain_id,
                "round": round_no,
                "speakers": [r.character_id for r in chosen],
            })
            for result in chosen:
                if self.is_cancelled(room.id):
                    reason = "cancelled"
                    break
                if calls_used + 1 > MAX_CHAIN_CALLS:
                    reason = "max_calls"
                    break
                character = next(
                    (c for c in members if c.id == result.character_id), None,
                )
                if character is None:
                    continue
                history, trigger = self._trigger_for(
                    room, user_input if first_speaker else None,
                )
                first_speaker = False
                await self.speak(
                    ws,
                    room=room,
                    character=character,
                    user_card=user_card,
                    history=history,
                    user_input=trigger,
                    should_stop=lambda: self.is_cancelled(room.id),
                )
                calls_used += 1
                last_speaker = result.character_id
            if reason in ("cancelled", "max_calls"):
                break
        else:
            reason = "max_rounds"

        await self._safe_send(ws, {
            "type": "group.chain.finished",
            "room_id": room.id,
            "chain_id": chain_id,
            "reason": reason,
        })
        return reason

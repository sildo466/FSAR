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
from src.utils.logger import logger

if TYPE_CHECKING:
    from src.memory.rooms import RoomStore
    from src.server.chat_engine import ChatEngine


UNKNOWN_SPEAKER = "Unknown"

# A chain has no round cap of its own: it runs until the group settles or the
# user stops it, so a room can hold an open-ended debate. Set rooms.max_rounds
# to a positive number when a particular room wants a bound.
UNLIMITED_ROUNDS = 0
EAGER_THRESHOLD = 5
SPEAKERS_PER_ROUND = 2
MENTIONED_EAGERNESS = 10
ELECT_HISTORY_LINES = 20
GROUP_SHORT_CACHE_LIMIT = 10

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

TURN_INSTRUCTION = (
    "{speaker} has just said this in the group chat:\n"
    "{text}\n\n"
    "Reply now, in character, with only your own next line."
)


_TOOL_CALL_RE = re.compile(
    r"<tool_call>.*?</tool_call>", re.DOTALL | re.IGNORECASE,
)
_TOOL_CALL_UNCLOSED_RE = re.compile(
    r"<tool_call>.*\Z", re.DOTALL | re.IGNORECASE,
)
_FUNCTION_CALL_RE = re.compile(
    r"<function_call>.*?</function_call>", re.DOTALL | re.IGNORECASE,
)


def strip_tool_call_markup(text: str) -> str:
    """Remove tool-call markup the model wrote into its visible reply.

    A group turn offers no tools and the prompt no longer advertises any, but
    the syntax is in the model's training data, so "do not emit this" is only a
    probability. Strip it, and let a reply that was nothing but a tool call fall
    through to the blank-reply path so no bubble is created."""
    cleaned = _TOOL_CALL_RE.sub("", text)
    cleaned = _FUNCTION_CALL_RE.sub("", cleaned)
    cleaned = _TOOL_CALL_UNCLOSED_RE.sub("", cleaned)
    return cleaned.strip()


def turn_instruction(text: str, speaker: str = "") -> str:
    """Wrap the trigger as a direct instruction to this speaker.

    A bare transcript line reads as more script for the model to continue,
    which makes it write the other characters' lines too."""
    if not speaker:
        return text
    return TURN_INSTRUCTION.format(speaker=speaker, text=text)


def strip_speaker_marker(text: str, own_name: str) -> str:
    """Drop a leading "[OwnName]:" the model copied from the transcript.

    The marker is an input convention, but models sometimes continue it instead
    of just answering, and the copy then compounds over rounds. Prompt wording
    only makes this less likely, never impossible, so clean it deterministically.

    Only the speaker's *own* name is stripped, so stage directions such as
    "[笑]：" in other brackets survive untouched."""
    name = (own_name or "").strip()
    if not name:
        return text
    pattern = re.compile(r"^\s*\[\s*" + re.escape(name) + r"\s*\]\s*[:：]\s*")
    cleaned = text
    while True:
        stripped = pattern.sub("", cleaned, count=1)
        if stripped == cleaned:
            return cleaned.lstrip()
        cleaned = stripped


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

    def _bound_short_cache(self, conv_id: str) -> None:
        """_save_assistant -> _ensure_short hydrates the room's whole history
        into the shared short cache and holds an LRU slot for it, but a group
        turn builds its history from the room and never reads that cache, so a
        long-lived room would grow the deque forever."""
        queue = self.chat._short_cache.get(conv_id)
        if queue is not None and len(queue) > GROUP_SHORT_CACHE_LIMIT:
            del queue[: len(queue) - GROUP_SHORT_CACHE_LIMIT]

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
        trigger_speaker: str = "",
        message_id: str | None = None,
        replace_row_id: int | None = None,
    ) -> tuple[str, str]:
        """One character's turn: in-character prompt, one streaming call.

        Returns (message_id, text). Memory cleansing is deliberately skipped —
        it costs an extra model call per speaker per round.

        With replace_row_id the turn rewrites that row in place instead of
        appending, so a regenerate neither duplicates the bubble nor moves it
        to the end of the room."""
        chat = self.chat
        conv_id = room.session_id
        message_id = message_id or f"group_{uuid.uuid4().hex[:12]}"
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
            group_mode=True,
        )
        client, model, provider_id = chat.client_and_model()
        _, max_output = chat._model_limits()
        messages: list[Any] = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        if user_input:
            messages.append({
                "role": "user",
                "content": turn_instruction(user_input, trigger_speaker),
            })

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
        text = strip_tool_call_markup(strip_speaker_marker(text, char_name or ""))
        if not text.strip():
            # The call produced nothing, or only a speaker marker. Saving a
            # blank row would leave an empty bubble in the room and feed the
            # character's memory an empty turn. On a regenerate this also leaves
            # the original reply intact, which is the right trade.
            await self._safe_send(ws, {
                "type": "group.speaker.done",
                "room_id": room.id,
                "message_id": message_id,
                "failed": True,
                "content": "",
            })
            return message_id, ""
        row_id = replace_row_id
        if replace_row_id is not None:
            if chat.session_store.update_message(
                replace_row_id, text, character_card_id=char_id,
            ):
                chat._msg_ids[message_id] = replace_row_id
            else:
                row_id = None
        if row_id is None:
            chat._save_assistant(
                message_id, conv_id, text, character_id=char_id,
            )
            row_id = chat._msg_ids.get(message_id)
        self._bound_short_cache(conv_id)
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
            "row_id": row_id,
            # Authoritative text: the streamed deltas were emitted before the
            # marker was stripped, and a failed call appends its own suffix.
            "content": text,
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
    ) -> tuple[list[dict[str, str]], str, str]:
        """History for the next speaker, the text that triggered them, and who
        said it ("" when the trigger is the user's opening line).

        The trigger is returned raw and kept out of history: it goes back as an
        explicit instruction, not as another transcript line, otherwise the
        model reads the transcript as a script and writes other people's
        lines too."""
        chat = self.chat
        rows = chat.session_store.get_session_messages(room.session_id)
        names, user_name = self._speaker_names(room)
        if first_input is not None:
            if rows and rows[-1].role == "user":
                rows = rows[:-1]
            history = format_group_history(
                rows, names_by_id=names, user_name=user_name,
            )
            return history, first_input, ""
        if not rows:
            return [], "", ""
        last = rows[-1]
        speaker = (
            user_name if last.role == "user"
            else names.get(last.character_card_id or -1, UNKNOWN_SPEAKER)
        )
        history = format_group_history(
            rows[:-1], names_by_id=names, user_name=user_name,
        )
        return history, last.content, speaker

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

        last_speaker: int | None = None
        first_speaker = True
        reason = "settled"
        max_rounds = max(0, int(getattr(room, "max_rounds", 0) or 0))
        round_no = 0

        try:
            while True:
                # Checked once per round so Stop stays responsive on a long
                # chain, not just between speakers.
                if self.is_cancelled(room.id):
                    reason = "cancelled"
                    break
                round_no += 1
                if max_rounds and round_no > max_rounds:
                    reason = "max_rounds"
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
                eager = [r for r in results if r.eagerness >= EAGER_THRESHOLD]
                if not eager:
                    reason = "settled"
                    break
                chosen = [
                    r for r in eager if r.character_id != last_speaker
                ][:SPEAKERS_PER_ROUND]
                if not chosen:
                    reason = "settled"
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
                    character = next(
                        (c for c in members if c.id == result.character_id), None,
                    )
                    if character is None:
                        continue
                    history, trigger, trigger_speaker = self._trigger_for(
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
                        trigger_speaker=trigger_speaker,
                    )
                    last_speaker = result.character_id
                if reason == "cancelled":
                    break
        except asyncio.CancelledError:
            reason = "cancelled"
            raise
        except Exception as e:
            logger.warning(f"group chain failed: {e}")
            reason = "error"
        finally:
            # Must always fire: the client gates its composer on chainRunning,
            # which only this event clears.
            await self._safe_send(ws, {
                "type": "group.chain.finished",
                "room_id": room.id,
                "chain_id": chain_id,
                "reason": reason,
            })
        return reason

    async def regenerate(
        self,
        ws: Any,
        *,
        room: Any,
        message_row_id: int,
        user_card: Any,
    ) -> tuple[str, str] | None:
        """Re-run one character's turn in place.

        No election and no chaining: this is the user asking a specific speaker
        to say it again, not a new round."""
        chat = self.chat
        rows = chat.session_store.get_session_messages(room.session_id)
        index = next(
            (i for i, r in enumerate(rows) if r.id == message_row_id), None,
        )
        if index is None:
            return None
        target = rows[index]
        if target.role != "assistant" or not target.character_card_id:
            return None
        character = chat.card_repo.get_character(target.character_card_id)
        if character is None:
            return None

        prior = rows[:index]
        names, user_name = self._speaker_names(room)
        history = format_group_history(
            prior[:-1], names_by_id=names, user_name=user_name,
        )
        trigger = prior[-1].content if prior else ""
        trigger_speaker = ""
        if prior:
            trigger_speaker = (
                user_name if prior[-1].role == "user"
                else names.get(prior[-1].character_card_id or -1, UNKNOWN_SPEAKER)
            )

        self.clear_cancel(room.id)
        return await self.speak(
            ws,
            room=room,
            character=character,
            user_card=user_card,
            history=history,
            user_input=trigger,
            should_stop=lambda: self.is_cancelled(room.id),
            trigger_speaker=trigger_speaker,
            message_id=str(message_row_id),
            replace_row_id=message_row_id,
        )

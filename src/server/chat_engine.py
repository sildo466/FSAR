# SPDX-License-Identifier: Apache-2.0
"""GUI chat engine — reuses the CLI LLM/tool/memory stack over the WS transport."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections import OrderedDict, deque
from pathlib import Path
from typing import Any

from fastapi import WebSocket

from src.core.experience_injector import ExperienceIndexInjector
from src.core.prompts import build_system_prompt
from src.core.strategy_injector import StrategyInjector
from src.memory import (
    DecisionLog,
    FeedbackStore,
    IdleReflector,
    LongTermMemory,
    MemoryRecall,
    ReflectionStore,
    SemanticMemory,
    SessionStore,
    ShortTermMemory,
    TaskReflector,
    UserModel,
    clear_task_context,
    set_task_context,
)
from src.memory.cards import CardRepo
from src.mcp import MCPManager
from src.security import (
    RiskEngine,
    append_entry,
    load_permissions,
    make_entry,
    save_permissions,
)
from src.security.confirmation import ConfirmResponse
from src.server.risk_bridge import RiskBridge
from src.server.title_generator import TitleGenerator
from src.tools import ToolRegistry, create_default_registry
from src.utils.fsar_config import FsarConfig
from src.providers.llm.deepseek import is_deepseek_official, prepare_messages as deepseek_prepare_messages
from src.utils.llm_factory import cached_chat_completion, make_llm_client
from src.utils.logger import logger

MAX_TOOL_TURNS = 50
DELTA_CHUNK = 120
SHORT_TERM_LIMIT = 10
SHORT_TERM_LRU = 50


class ChatEngine:
    """One per server process. Owns the same subsystem instances the CLI builds."""

    def __init__(self, config: FsarConfig, bridge: RiskBridge) -> None:
        self.config = config
        self.bridge = bridge
        self.registry: ToolRegistry = create_default_registry()
        self.mcp = MCPManager(
            self.registry,
            config_path=config.get("mcp.config_path", "config/mcp_servers.yaml"),
            fsar_servers=config.get_mcp_servers(),
        )
        self.permissions = load_permissions()
        self.risk_engine = RiskEngine(self.permissions)
        self.long_memory = LongTermMemory()
        self.semantic = SemanticMemory()
        self.user_model = UserModel()
        self.feedback = FeedbackStore()
        self.recall = MemoryRecall(
            long_term=self.long_memory,
            semantic=self.semantic,
            user_model=self.user_model,
            feedback=self.feedback,
        )
        self.reflection_store = ReflectionStore()
        self.task_reflector = TaskReflector(
            store=self.reflection_store,
            user_model=self.user_model,
            intensity=config.reflection_intensity,
            triggers=config.reflection_triggers,
        )
        self.idle_reflector = IdleReflector(
            long_term=self.long_memory,
            user_model=self.user_model,
            feedback=self.feedback,
            intensity=config.reflection_intensity,
        )
        self.decision_log = DecisionLog()
        self.strategy_injector = StrategyInjector(
            decision_log=self.decision_log,
            user_model=self.user_model,
            intensity=config.reflection_intensity,
        )
        self.experience_injector = ExperienceIndexInjector(
            intensity=config.reflection_intensity,
        )
        self.session_store = SessionStore(
            config.get("memory.sqlite_path", "data/memory.db")
        )
        self.card_repo = CardRepo(
            Path(config.get("memory.sqlite_path", "data/memory.db"))
        )
        with self.card_repo._connect() as _conn:
            self.card_repo.ensure_tables(_conn)
        self.title_generator = TitleGenerator(
            config=config,
            store=self.session_store,
            client_factory=self.client_and_model,
            push_event=self._broadcast,
        )

        self._msg_ids: dict[str, int] = {}
        self._conv_locks: dict[str, asyncio.Lock] = {}
        self._short_cache: OrderedDict[str, deque[dict[str, Any]]] = OrderedDict()
        self._cancelled = False
        self._mcp_started = False

    # ---------- session lifecycle ----------

    def active_conversation_id(self) -> str | None:
        return getattr(self, "_active_conv_id", None)

    async def switch_conversation(self, conversation_id: str) -> bool:
        row = self.session_store.get(conversation_id)
        if row is None:
            return False
        self._active_conv_id = conversation_id
        self._short_cache.pop(conversation_id, None)
        self._hydrate_short(conversation_id)
        return True

    def new_conversation(self) -> str:
        row = self.session_store.create()
        self._active_conv_id = row.id
        return row.id

    def ensure_conversation(self, conversation_id: str | None) -> str:
        """Return a valid conversation_id, creating one if needed."""
        if conversation_id and self.session_store.get(conversation_id):
            return conversation_id
        return self.new_conversation()

    def _hydrate_short(self, conversation_id: str, limit: int = SHORT_TERM_LIMIT) -> None:
        rows = self.session_store.get_recent_messages(conversation_id, limit=limit)
        dq: deque[dict[str, Any]] = deque(maxlen=limit)
        for r in rows:
            dq.append({"role": r.role, "content": r.content})
        self._short_cache[conversation_id] = dq
        self._short_cache.move_to_end(conversation_id)
        while len(self._short_cache) > SHORT_TERM_LRU:
            self._short_cache.popitem(last=False)

    def _lock_for(self, conversation_id: str) -> asyncio.Lock:
        lock = self._conv_locks.get(conversation_id)
        if lock is None:
            lock = asyncio.Lock()
            self._conv_locks[conversation_id] = lock
        return lock

    async def _broadcast(self, event: dict[str, Any]) -> None:
        """Push a server event to all live websockets (if any)."""
        try:
            from src.server.handlers.chat import _broadcast
            await _broadcast(event)
        except Exception as e:
            logger.debug(f"broadcast skipped: {e}")

    async def _run_idle_reflection_if_due(self) -> None:
        """Check GUI-configured idle_batch triggers; run reflection if due."""
        try:
            intensity = self.config.reflection_intensity
            if intensity != self.idle_reflector.intensity:
                self.idle_reflector.set_intensity(intensity)
                self.task_reflector.set_intensity(intensity)
            self.task_reflector.set_triggers(self.config.reflection_triggers)
            triggers = self.config.reflection_triggers
            if not self.idle_reflector.should_reflect_by_triggers(triggers):
                return
            if self.idle_reflector.intensity == "off":
                return
            promoted_count = await asyncio.to_thread(self._do_idle_reflect)
            if promoted_count > 0:
                await self._broadcast_experiences(promoted_count)
        except Exception as e:
            logger.warning(f"idle reflection check failed: {e}")

    def _do_idle_reflect(self) -> int:
        """Run the idle reflector synchronously (off the event loop).

        Returns the count of newly promoted experiences so the caller
        can broadcast them to live websockets."""
        client, model = self.client_and_model()
        if client is not None:
            try:
                self.idle_reflector.set_llm(client)
                self.idle_reflector._model = model  # noqa: SLF001
            except Exception as e:
                logger.debug(f"idle reflector set_llm failed: {e}")

        # Sync the GUI-configured threshold_hours so the legacy time gate
        # inside IdleReflector.reflect() honours the user's setting.
        cfg_hours = float(
            self.config.get("reflection.triggers.idle_batch.threshold_hours", 12) or 12
        )
        if cfg_hours > 0:
            self.idle_reflector.interval_hours = cfg_hours

        promoted_count = 0
        try:
            # _run_idle_reflection_if_due already validated the GUI trigger;
            # force=True bypasses the legacy should_reflect() gate so the
            # user's threshold_hours/threshold_events are authoritative.
            report = self.idle_reflector.reflect(force=True)
            if self.idle_reflector.intensity == "high":
                from src.memory.experience_store import ExperienceStore
                promoted_count = ExperienceStore().auto_promote(threshold=3)
        except Exception as e:
            logger.warning(f"idle reflector failed: {e}")
            return 0
        logger.info(
            f"idle reflection done: profile={len(report.profile) if report else 0}, "
            f"promoted={promoted_count}"
        )
        return promoted_count

    async def _broadcast_experiences(self, count: int) -> None:
        from src.memory.experience_store import ExperienceStore
        if count <= 0:
            return
        try:
            store = ExperienceStore()
            rows = store.list_for_index()
            for r in rows[-count:]:
                if not hasattr(r, "to_dict"):
                    continue
                await self._broadcast({
                    "type": "experience.created",
                    "experience": r.to_dict(),
                })
        except Exception as e:
            logger.debug(f"broadcast experiences skipped: {e}")

    async def start_mcp(self) -> None:
        if self._mcp_started:
            return
        self._mcp_started = True
        try:
            await self.mcp.start()
        except Exception as e:
            logger.warning(f"MCP startup failed: {e}")

    # ---------- LLM access ----------

    def client_and_model(self) -> tuple[Any, str]:
        active_id = self.config.get("llm.active", "")
        if not active_id:
            return None, ""
        provider = self.config.get_llm_config(active_id)
        model = provider.get("model", "")
        if not model:
            return None, ""
        try:
            return make_llm_client(active_id), model
        except Exception as e:
            logger.error(f"LLM client init failed: {e}")
            return None, ""

    # ---------- public entry points ----------

    def cancel(self) -> None:
        self._cancelled = True

    def rate(self, message_id: str, score: int, reason: str = "") -> dict[str, Any]:
        msg_id = self._msg_ids.get(message_id)
        if msg_id is None:
            return {"status": "no_message"}
        self.feedback.add_or_update_rating(
            message_id=msg_id,
            session_id=self._active_conv_id or "",
            rating=score,
            reason=reason,
        )
        if reason:
            tag = "positive" if score >= 4 else ("negative" if score <= 2 else "neutral")
            try:
                self.user_model.record_pattern(
                    f"User {tag} feedback: {reason[:60]}",
                    f"Rated {score}/5, reason: {reason}",
                )
            except Exception as e:
                logger.debug(f"pattern record skipped: {e}")
        return {"status": "ok", "db_id": msg_id}

    async def handle_send(
        self, ws: WebSocket, content: str, mode: str,
        conversation_id: str | None = None,
        character_id: int | None = None,
    ) -> None:
        if conversation_id and self.session_store.get(conversation_id):
            conv_id = conversation_id
        else:
            row = self.session_store.create()
            conv_id = row.id
            await ws.send_json({
                "type": "conversation.created",
                "session": row.to_dict(),
            })
        self._active_conv_id = conv_id
        if character_id is not None:
            requested_character = self.card_repo.get_character(character_id)
            if requested_character is not None:
                self.session_store.set_character(conv_id, requested_character.id)
        char_id = self.session_store.get_character(conv_id)
        character = self.card_repo.get_character(char_id) if char_id else None
        if character is None:
            character = self.card_repo.get_default_character()
            if character is not None:
                self.session_store.set_character(conv_id, character.id)
        char_name = character.name if character else "Assistant"
        async with self._lock_for(conv_id):
            self._cancelled = False
            message_id = f"msg_{uuid.uuid4().hex[:8]}"
            await ws.send_json({
                "type": "chat.thinking",
                "message_id": message_id,
                "conversation_id": conv_id,
                "character_id": character.id if character else None,
                "character_name": char_name,
            })
            try:
                if content.strip().startswith("/"):
                    from src.server.handlers import commands
                    text = await commands.execute(self, content.strip())
                    await self._emit_text(ws, message_id, text, save=False)
                    await self._done(ws, message_id, "success", conv_id=conv_id)
                    return
                client, model = self.client_and_model()
                if client is None:
                    await ws.send_json({
                        "type": "error", "code": "no_provider",
                        "message": "No active LLM provider — configure one in Settings.",
                        "recoverable": True,
                    })
                    await self._done(ws, message_id, "failure", conv_id=conv_id)
                    return
                self._save_user(conv_id, content)
                if mode == "companion":
                    await self._run_companion(ws, message_id, client, model, conv_id, content, character, char_name)
                else:
                    await self._run_agent(ws, message_id, client, model, conv_id, content, character, char_name)
            except Exception as e:
                logger.error(f"chat.send failed: {e}")
                await ws.send_json({
                    "type": "error", "code": "chat_failed",
                    "message": str(e), "recoverable": True,
                })
                await self._done(ws, message_id, "failure", conv_id=conv_id)

    # ---------- agent mode ----------

    async def _run_agent(self, ws: WebSocket, message_id: str, client: Any,
                         model: str, conv_id: str, user_input: str,
                         character: Any = None, char_name: str | None = None) -> None:
        tools = self.registry.get_tools_for_llm()
        system_prompt = self._build_prompt(conv_id, "agent", user_input)
        messages: list[Any] = [{"role": "system", "content": system_prompt}]
        self._ensure_short(conv_id)
        messages.extend(self._short_cache[conv_id])
        messages.append({"role": "user", "content": user_input})
        deepseek = is_deepseek_official(str(getattr(client, "base_url", "") or ""))

        task_id = f"gui_{uuid.uuid4().hex[:12]}"
        set_task_context(task_id=task_id, session_id=conv_id)
        final_text = ""
        outcome = "success"
        try:
            for _ in range(MAX_TOOL_TURNS):
                if self._cancelled:
                    outcome = "failure"
                    final_text = "(Cancelled.)"
                    break
                call_kwargs: dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                    "tools": tools if tools else None,
                    "tool_choice": "auto" if tools else None,
                    "max_tokens": 4096,
                }
                if deepseek:
                    call_kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
                resp = await asyncio.to_thread(
                    cached_chat_completion,
                    client,
                    **call_kwargs,
                )
                self._record_llm_usage(task_id, resp)
                message = resp.choices[0].message
                if not message.tool_calls:
                    final_text = message.content or ""
                    break
                if deepseek:
                    messages.extend(deepseek_prepare_messages([message]))
                else:
                    messages.append(message)
                for tool_call in message.tool_calls:
                    func_name = tool_call.function.name
                    try:
                        func_args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        func_args = {}
                    result = await self._execute_guarded(
                        ws, message_id, tool_call.id, func_name, func_args, conv_id,
                    )
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    })
            else:
                final_text = "(Reached max tool turns without a final summary.)"
        except Exception as e:
            logger.error(f"Agent loop error: {e}")
            outcome = "failure"
            final_text = f"Tool execution failed: {e}"
        finally:
            clear_task_context()

        await self._emit_text(ws, message_id, final_text, conv_id=conv_id)
        await self._done(ws, message_id, outcome, conv_id=conv_id)
        await asyncio.to_thread(self._reflect, task_id, conv_id, user_input, outcome)
        self._maybe_title(conv_id, user_input)
        self.idle_reflector.bump_event()
        await self._run_idle_reflection_if_due()

    async def _execute_guarded(self, ws: WebSocket, message_id: str, call_id: str,
                               name: str, args: dict, conv_id: str) -> str:
        tool = self.registry.get(name)
        if tool is None:
            return f"Error: Unknown tool '{name}'"

        verdict = self.risk_engine.evaluate(tool, args)
        needs_confirm = verdict.needs_confirm() and not verdict.is_denied()
        await ws.send_json({
            "type": "chat.tool_call",
            "message_id": message_id,
            "call_id": call_id,
            "tool": name,
            "args": args,
            "risk": verdict.effective_risk if needs_confirm else "SAFE",
        })
        user_response = ""

        async def _result(result: str, latency_ms: int = 0) -> str:
            await ws.send_json({
                "type": "chat.tool_result",
                "call_id": call_id,
                "result": result if isinstance(result, str) else str(result),
                "latency_ms": latency_ms,
            })
            return result

        if verdict.is_denied():
            append_entry(make_entry(
                session=conv_id, tool=name, args=args,
                risk=verdict.effective_risk, verdict="deny",
                user_response="", outcome="denied",
            ))
            return await _result(f"[DENIED] {verdict.reason}")

        if needs_confirm:
            args_preview = json.dumps(args, ensure_ascii=False)[:400]
            response = await self.bridge.submit(
                call_id, name, args_preview, verdict.reason, timeout=300.0,
            )
            user_response = response.value
            if response == ConfirmResponse.ALL:
                self.permissions.set_session_trust(name)
            elif response == ConfirmResponse.SERVER_TRUST:
                server_name = getattr(tool, "server_name", None)
                if server_name:
                    self.permissions.set_server_trust(server_name)
            elif response in (ConfirmResponse.NO, ConfirmResponse.NEVER):
                if response == ConfirmResponse.NEVER:
                    self.permissions.set_permanent_deny(name)
                    save_permissions(self.permissions)
                append_entry(make_entry(
                    session=conv_id, tool=name, args=args,
                    risk=verdict.effective_risk, verdict="confirm",
                    user_response=user_response, outcome="cancelled",
                ))
                return await _result(
                    f"[NEVER] {name} permanently denied ({verdict.reason})"
                    if response == ConfirmResponse.NEVER
                    else "[CANCELLED] User declined"
                )

        start = time.monotonic()
        try:
            result = await self.registry.execute(name, **args)
            error = None
            tool_outcome = "success"
        except Exception as e:
            result = f"Error: {e}"
            error = str(e)
            tool_outcome = "error"
        duration_ms = int((time.monotonic() - start) * 1000)

        append_entry(make_entry(
            session=conv_id, tool=name, args=args,
            risk=verdict.effective_risk,
            verdict="confirm" if needs_confirm else "proceed",
            user_response=user_response or "auto",
            outcome=tool_outcome, error=error, duration_ms=duration_ms,
        ))
        return await _result(result, duration_ms)

    # ---------- companion mode ----------

    async def _run_companion(self, ws: WebSocket, message_id: str, client: Any,
                             model: str, conv_id: str, user_input: str,
                             character: Any = None, char_name: str | None = None) -> None:
        system_prompt = self._build_prompt(conv_id, "companion", user_input)
        messages: list[dict] = [{"role": "system", "content": system_prompt}]
        self._ensure_short(conv_id)
        messages.extend(self._short_cache[conv_id])
        messages.append({"role": "user", "content": user_input})
        deepseek = is_deepseek_official(str(getattr(client, "base_url", "") or ""))

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        full: list[str] = []

        def _pump() -> None:
            try:
                stream_kwargs: dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                    "max_tokens": 65536,
                    "stream": True,
                    "cache_enabled": False,
                }
                if deepseek:
                    stream_kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
                stream = cached_chat_completion(client, **stream_kwargs)
                for chunk in stream:
                    if self._cancelled:
                        break
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta.content or ""
                    if delta:
                        loop.call_soon_threadsafe(queue.put_nowait, delta)
            except Exception as e:
                loop.call_soon_threadsafe(
                    queue.put_nowait, f"\nLLM call failed: {e}"
                )
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        pump = loop.run_in_executor(None, _pump)
        while True:
            delta = await queue.get()
            if delta is None:
                break
            full.append(delta)
            await ws.send_json({
                "type": "chat.delta", "message_id": message_id, "content": delta,
                "character_id": character.id if character else None,
                "character_name": char_name,
            })
        await pump
        text = "".join(full)
        self._save_assistant(message_id, conv_id, text)
        await self._done(ws, message_id, "success", conv_id=conv_id)
        self._maybe_title(conv_id, user_input)
        self.idle_reflector.bump_event()
        await self._run_idle_reflection_if_due()

    # ---------- helpers ----------

    async def _emit_text(self, ws: WebSocket, message_id: str, text: str,
                         *, save: bool = True, conv_id: str | None = None) -> None:
        text = text or "(Task ended.)"
        char_name = None
        char_id = None
        if conv_id:
            try:
                cid = self.session_store.get_character(conv_id)
                c = self.card_repo.get_character(cid) if cid else None
                if c:
                    char_id, char_name = c.id, c.name
            except Exception:
                pass
        for i in range(0, len(text), DELTA_CHUNK):
            await ws.send_json({
                "type": "chat.delta",
                "message_id": message_id,
                "content": text[i:i + DELTA_CHUNK],
                "character_id": char_id,
                "character_name": char_name,
            })
        if save:
            cid = conv_id or self._active_conv_id
            if cid:
                self._save_assistant(message_id, cid, text)

    def _post_turn_emotion_pass(self, conv_id: str) -> dict | None:
        from src.core.formula_engine import execute_emotion_formulas
        char_id = self.session_store.get_character(conv_id)
        character = self.card_repo.get_character(char_id) if char_id else None
        if character is None:
            character = self.card_repo.get_default_character()
        if character is None:
            return None
        schema = self.card_repo.get_emotion_schema(character.id)
        formulas = self.card_repo.get_emotion_formulas(character.id)
        state = self.card_repo.get_emotion_state(character.id)
        if not state or not formulas:
            return None
        new_state = execute_emotion_formulas(schema, formulas, state)
        self.card_repo.set_emotion_state(character.id, new_state)
        return new_state

    async def _done(self, ws: WebSocket, message_id: str, outcome: str,
                    conv_id: str | None = None) -> None:
        emotion_state = None
        char_id = None
        char_name = None
        if conv_id is not None:
            try:
                emotion_state = self._post_turn_emotion_pass(conv_id)
            except Exception as e:
                logger.debug(f"Post-turn emotion pass skipped: {e}")
            try:
                cid = self.session_store.get_character(conv_id)
                c = self.card_repo.get_character(cid) if cid else None
                if c:
                    char_id, char_name = c.id, c.name
            except Exception:
                pass
        payload = {
            "type": "chat.done", "message_id": message_id,
            "outcome": outcome, "summary": "",
        }
        if emotion_state is not None:
            payload["emotion_state"] = emotion_state
        payload["character_id"] = char_id
        payload["character_name"] = char_name
        await ws.send_json(payload)

    def _ensure_short(self, conv_id: str) -> None:
        if conv_id not in self._short_cache:
            self._hydrate_short(conv_id)
        else:
            self._short_cache.move_to_end(conv_id)

    def _save_user(self, conv_id: str, content: str) -> None:
        self._ensure_short(conv_id)
        dq = self._short_cache[conv_id]
        dq.append({"role": "user", "content": content})
        try:
            self.session_store.append_message(
                conv_id, "user", content, tags="query",
            )
            self.semantic.add(content, session_id=conv_id,
                              role="user", tags=["query"])
        except Exception as e:
            logger.warning(f"save user message failed: {e}")

    def _save_assistant(self, message_id: str, conv_id: str, content: str) -> None:
        self._ensure_short(conv_id)
        self._short_cache[conv_id].append({"role": "assistant", "content": content})
        try:
            msg_id = self.session_store.append_message(
                conv_id, "assistant", content, tags="reply",
            )
            if msg_id is not None:
                self._msg_ids[message_id] = msg_id
            self.semantic.add(content, session_id=conv_id,
                              role="assistant", tags=["reply"])
        except Exception as e:
            logger.warning(f"save assistant message failed: {e}")

    def _maybe_title(self, conv_id: str, user_input: str) -> None:
        """Trigger title generation once per conversation — after the
        first assistant reply completes. Skip if a title already exists."""
        row = self.session_store.get(conv_id)
        if row is None or row.title:
            return
        self.title_generator.schedule(conv_id, user_input)

    def _record_llm_usage(self, task_id: str, resp: Any) -> None:
        try:
            usage = getattr(resp, "usage", None)
            if usage is None:
                return
            get = (usage.get if isinstance(usage, dict)
                   else lambda k, d=0: getattr(usage, k, d) or d)
            self.decision_log.record(
                task_id=task_id,
                session_id=self._active_conv_id or "",
                step_no=0,
                chosen_tool="chat.llm",
                args_summary="",
                latency_ms=0,
                success=True,
                prompt_tokens=int(get("prompt_tokens", 0) or 0),
                completion_tokens=int(get("completion_tokens", 0) or 0),
                cached_tokens=int(get("cached_tokens", 0) or 0),
            )
        except Exception as e:
            logger.debug(f"usage record skipped: {e}")

    def _reflect(self, task_id: str, conv_id: str, user_input: str,
                outcome: str) -> None:
        try:
            decisions = self.decision_log.get_for_task(task_id)
            history = [
                {
                    "step": d.step_no,
                    "action": d.chosen_tool,
                    "params": {"args": d.args_summary},
                    "result": "success" if d.success else None,
                    "error": d.error_class or None,
                }
                for d in decisions
            ]
            self.task_reflector.reflect(
                task_id=task_id,
                session_id=conv_id,
                task=user_input,
                outcome=outcome,
                history=history,
            )
        except Exception as e:
            logger.debug(f"Task reflection skipped: {e}")

    def _build_prompt(self, conv_id: str, mode: str, user_input: str) -> str:
        char_id = self.session_store.get_character(conv_id)
        character = None
        if char_id is not None:
            character = self.card_repo.get_character(char_id)
        if character is None:
            character = self.card_repo.get_default_character()
        user_card = self.card_repo.get_default_user_card()
        return build_system_prompt(
            mode=mode,
            character=character,
            user_card=user_card,
            memory_block=self._memory_block(user_input),
            strategy_block=self._strategy_block(),
            experience_block=self._experience_block(),
        )

    def _memory_block(self, query: str) -> str:
        try:
            result = self.recall.recall_for_context(query, semantic_top_k=5)
            if result.is_empty:
                return ""
            max_chars = int(self.config.get("memory.recall_max_chars", 2000))
            return result.to_context(max_len=max_chars)
        except Exception as e:
            logger.warning(f"Memory recall failed: {e}")
            return ""

    def _strategy_block(self) -> str:
        try:
            recent = self.reflection_store.list_recent(limit=10)
            strategies = [
                r["suggested_strategy"] for r in recent if r.get("suggested_strategy")
            ]
            return self.strategy_injector.build_block(recent_strategies=strategies)
        except Exception as e:
            logger.debug(f"Strategy block build skipped: {e}")
            return ""

    def _experience_block(self) -> str:
        try:
            return self.experience_injector.build_block()
        except Exception as e:
            logger.debug(f"Experience block build skipped: {e}")
            return ""

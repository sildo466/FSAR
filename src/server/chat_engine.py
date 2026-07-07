# SPDX-License-Identifier: Apache-2.0
"""GUI chat engine — reuses the CLI LLM/tool/memory stack over the WS transport."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any

from fastapi import WebSocket

from src.core.experience_injector import ExperienceIndexInjector
from src.core.prompts import AGENT_SYSTEM_PROMPT, COMPANION_SYSTEM_PROMPT
from src.core.strategy_injector import StrategyInjector
from src.memory import (
    DecisionLog,
    FeedbackStore,
    LongTermMemory,
    MemoryRecall,
    ReflectionStore,
    SemanticMemory,
    ShortTermMemory,
    TaskReflector,
    UserModel,
    clear_task_context,
    set_task_context,
)
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
from src.tools import ToolRegistry, create_default_registry
from src.utils.fsar_config import FsarConfig
from src.utils.llm_factory import cached_chat_completion, make_llm_client
from src.utils.logger import logger

MAX_TOOL_TURNS = 50
DELTA_CHUNK = 120


class ChatEngine:
    """One per server process. Owns the same subsystem instances the CLI builds."""

    def __init__(self, config: FsarConfig, bridge: RiskBridge) -> None:
        self.config = config
        self.bridge = bridge
        self.registry: ToolRegistry = create_default_registry()
        self.mcp = MCPManager(
            self.registry,
            config_path=config.get("mcp.config_path", "config/mcp_servers.yaml"),
        )
        self.permissions = load_permissions()
        self.risk_engine = RiskEngine(self.permissions)
        self.short_memory = ShortTermMemory()
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
        self.session_id = uuid.uuid4().hex[:8]
        self._lock = asyncio.Lock()
        self._cancelled = False
        self._msg_ids: dict[str, int] = {}
        self._mcp_started = False

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

    def rate(self, message_id: str, score: int, reason: str = "") -> str:
        msg_id = self._msg_ids.get(message_id)
        if msg_id is None:
            return "no_message"
        self.feedback.add_or_update_rating(
            message_id=msg_id,
            session_id=self.session_id,
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
        return "ok"

    async def handle_send(self, ws: WebSocket, content: str, mode: str) -> None:
        async with self._lock:
            self._cancelled = False
            message_id = f"msg_{uuid.uuid4().hex[:8]}"
            await ws.send_json({"type": "chat.thinking", "message_id": message_id})
            try:
                if content.strip().startswith("/"):
                    from src.server.handlers import commands
                    text = await commands.execute(self, content.strip())
                    await self._emit_text(ws, message_id, text, save=False)
                    await self._done(ws, message_id, "success")
                    return
                client, model = self.client_and_model()
                if client is None:
                    await ws.send_json({
                        "type": "error", "code": "no_provider",
                        "message": "No active LLM provider — configure one in Settings.",
                        "recoverable": True,
                    })
                    await self._done(ws, message_id, "failure")
                    return
                self._save_user(content)
                if mode == "companion":
                    await self._run_companion(ws, message_id, client, model, content)
                else:
                    await self._run_agent(ws, message_id, client, model, content)
            except Exception as e:
                logger.error(f"chat.send failed: {e}")
                await ws.send_json({
                    "type": "error", "code": "chat_failed",
                    "message": str(e), "recoverable": True,
                })
                await self._done(ws, message_id, "failure")

    # ---------- agent mode (tool loop, mirrors CLI _handle_tool_task) ----------

    async def _run_agent(self, ws: WebSocket, message_id: str, client: Any,
                         model: str, user_input: str) -> None:
        tools = self.registry.get_tools_for_llm()
        messages: list[Any] = [{"role": "system", "content": AGENT_SYSTEM_PROMPT}]
        for block in (
            self._memory_block(user_input),
            self._strategy_block(),
            self._experience_block(),
        ):
            if block:
                messages.append({"role": "system", "content": block})
        messages.extend(self.short_memory.get_context_for_llm(last_n=20))
        messages.append({"role": "user", "content": user_input})

        task_id = f"gui_{uuid.uuid4().hex[:12]}"
        set_task_context(task_id=task_id, session_id=self.session_id)
        final_text = ""
        outcome = "success"
        try:
            for _ in range(MAX_TOOL_TURNS):
                if self._cancelled:
                    outcome = "failure"
                    final_text = "(Cancelled.)"
                    break
                resp = await asyncio.to_thread(
                    cached_chat_completion,
                    client,
                    model=model,
                    messages=messages,
                    tools=tools if tools else None,
                    tool_choice="auto" if tools else None,
                    max_tokens=4096,
                )
                self._record_llm_usage(task_id, resp)
                message = resp.choices[0].message
                if not message.tool_calls:
                    final_text = message.content or ""
                    break
                messages.append(message)
                for tool_call in message.tool_calls:
                    func_name = tool_call.function.name
                    try:
                        func_args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        func_args = {}
                    result = await self._execute_guarded(
                        ws, message_id, tool_call.id, func_name, func_args,
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

        await self._emit_text(ws, message_id, final_text)
        await self._done(ws, message_id, outcome)
        await asyncio.to_thread(self._reflect, task_id, user_input)

    async def _execute_guarded(self, ws: WebSocket, message_id: str, call_id: str,
                               name: str, args: dict) -> str:
        """Mirror of the CLI risk gate; confirmation goes through the WS RiskBridge."""
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
                session=self.session_id, tool=name, args=args,
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
                    session=self.session_id, tool=name, args=args,
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
            session=self.session_id, tool=name, args=args,
            risk=verdict.effective_risk,
            verdict="confirm" if needs_confirm else "proceed",
            user_response=user_response or "auto",
            outcome=tool_outcome, error=error, duration_ms=duration_ms,
        ))
        return await _result(result, duration_ms)

    # ---------- companion mode (streaming, mirrors CLI _handle_chat) ----------

    async def _run_companion(self, ws: WebSocket, message_id: str, client: Any,
                             model: str, user_input: str) -> None:
        messages: list[dict] = [{"role": "system", "content": COMPANION_SYSTEM_PROMPT}]
        for block in (self._memory_block(user_input), self._strategy_block(),
                      self._experience_block()):
            if block:
                messages.append({"role": "system", "content": block})
        messages.extend(self.short_memory.get_context_for_llm(last_n=20))
        messages.append({"role": "user", "content": user_input})

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        full: list[str] = []

        def _pump() -> None:
            try:
                stream = cached_chat_completion(
                    client, model=model, messages=messages,
                    max_tokens=65536, stream=True, cache_enabled=False,
                )
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
            })
        await pump
        text = "".join(full)
        self._save_assistant(message_id, text)
        await self._done(ws, message_id, "success")

    # ---------- helpers ----------

    async def _emit_text(self, ws: WebSocket, message_id: str, text: str,
                         *, save: bool = True) -> None:
        text = text or "(Task ended.)"
        for i in range(0, len(text), DELTA_CHUNK):
            await ws.send_json({
                "type": "chat.delta",
                "message_id": message_id,
                "content": text[i:i + DELTA_CHUNK],
            })
        if save:
            self._save_assistant(message_id, text)

    async def _done(self, ws: WebSocket, message_id: str, outcome: str) -> None:
        await ws.send_json({
            "type": "chat.done", "message_id": message_id,
            "outcome": outcome, "summary": "",
        })

    def _save_user(self, content: str) -> None:
        self.short_memory.add("user", content)
        try:
            self.long_memory.save_message(
                session_id=self.session_id, role="user", content=content,
            )
            self.semantic.add(content, session_id=self.session_id,
                              role="user", tags=["query"])
        except Exception as e:
            logger.warning(f"save user message failed: {e}")

    def _save_assistant(self, message_id: str, content: str) -> None:
        self.short_memory.add("assistant", content)
        try:
            msg_id = self.long_memory.save_message(
                session_id=self.session_id, role="assistant", content=content,
            )
            if msg_id is not None:
                self._msg_ids[message_id] = msg_id
            self.semantic.add(content, session_id=self.session_id,
                              role="assistant", tags=["reply"])
        except Exception as e:
            logger.warning(f"save assistant message failed: {e}")

    def _record_llm_usage(self, task_id: str, resp: Any) -> None:
        try:
            usage = getattr(resp, "usage", None)
            if usage is None:
                return
            get = (usage.get if isinstance(usage, dict)
                   else lambda k, d=0: getattr(usage, k, d) or d)
            self.decision_log.record(
                task_id=task_id,
                session_id=self.session_id,
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

    def _reflect(self, task_id: str, user_input: str) -> None:
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
            outcome = "success" if not any(not d.success for d in decisions) else "failure"
            self.task_reflector.reflect(
                task_id=task_id,
                session_id=self.session_id,
                task=user_input,
                outcome=outcome,
                history=history,
            )
        except Exception as e:
            logger.debug(f"Task reflection skipped: {e}")

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
            recent = self.reflection_store.list_recent(
                limit=10, session_id=self.session_id,
            )
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

"""Agent executor — runs user job prompts via isolated LLM turn.

Does NOT share state with the main chat session:
- Default tools_allow='' → all registered tools are exposed to the LLM
- An explicit tools_allow list restricts the exposed tools
- timeout enforced via asyncio.wait_for

The executor does not write to the store — service.py owns that. The
executor only invokes the LLM (and optional tools) and returns the result
text. Errors surface as exceptions so service can classify them.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from src.scheduler.types import ScheduledJob

logger = logging.getLogger(__name__)

# Tools that may NOT be invoked by scheduled jobs (HIGH/MEDIUM risk).
# These run unattended; RiskEngine.confirm can't gate them since no
# live user is present.
BLOCKED_TOOLS = frozenset({
    "run_command",
    "file_ops",
    "edit",
    "process",
})

# Cap on LLM round-trips per job so a tool-calling loop cannot run forever
# inside the job's timeout budget.
MAX_TOOL_ITERATIONS = 5


def _schema_name(schema: dict) -> str:
    return str((schema.get("function") or {}).get("name") or "")


def _safe_tool_names(raw: str) -> list[str]:
    """Parse tools_allow (JSON array string), drop blocked names."""
    if not raw:
        return []
    try:
        names = json.loads(raw)
    except Exception:
        return []
    if not isinstance(names, list):
        return []
    return [n for n in names if isinstance(n, str) and n not in BLOCKED_TOOLS]


def _model_override(job: ScheduledJob, primary_model: str) -> str:
    return job.model_override or primary_model


def _get(obj: Any, key: str, default: Any = None) -> Any:
    """Read a field from an SDK object or a plain dict response."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


class IsolatedExecutor:
    """Runs agent-kind jobs in isolation from the main chat session."""

    def __init__(
        self,
        *,
        llm_client_factory,
        primary_model: str,
        tool_registry=None,
        timeout_default: int = 60,
    ):
        self._llm_factory = llm_client_factory
        self._model = primary_model
        self._tools = tool_registry
        self._default_timeout = timeout_default

    async def run(self, job: ScheduledJob) -> str:
        """Execute the job's prompt via LLM. Returns the result text.

        Raises:
            asyncio.TimeoutError: if execution exceeds job.timeout_seconds
            PermissionError: if job.tools_allow contains blocked tools
            RuntimeError: on other LLM/tool failures
        """
        timeout = job.timeout_seconds or self._default_timeout
        client = self._llm_factory()
        model = _model_override(job, self._model)
        prompt = job.prompt.strip()
        if not prompt:
            raise ValueError(f"job {job.id} ({job.name}) has empty prompt")

        allowed_tools = _safe_tool_names(job.tools_allow)
        messages = [
            {"role": "system", "content": _system_message(allowed_tools)},
            {"role": "user", "content": prompt},
        ]

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": 4096,
        }
        if self._tools is not None:
            wanted = set(allowed_tools)
            schemas = [
                s for s in self._tools.get_tools_for_llm()
                if _schema_name(s) not in BLOCKED_TOOLS
                and (not wanted or _schema_name(s) in wanted)
            ]
            if schemas:
                kwargs["tools"] = schemas

        try:
            return await asyncio.wait_for(
                self._run_loop(client, kwargs, messages),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            raise
        except Exception as e:
            raise RuntimeError(f"LLM call failed: {e}") from e

    async def _run_loop(self, client, kwargs: dict, messages: list) -> str:
        """Drive the tool-call loop until the model answers with text."""
        for _ in range(MAX_TOOL_ITERATIONS):
            kwargs["messages"] = messages
            response = await self._call(client, kwargs)
            message = _first_message(response)
            calls = _get(message, "tool_calls") or []
            if not calls:
                return _extract_text(response)
            messages.append(_assistant_turn(message, calls))
            for call in calls:
                messages.append(await self._run_tool(call))

        # Tool budget spent — ask once more with tools withheld so the model
        # has to produce prose instead of another call.
        final_kwargs = {k: v for k, v in kwargs.items() if k != "tools"}
        final_kwargs["messages"] = messages
        return _extract_text(await self._call(client, final_kwargs))

    async def _run_tool(self, call: Any) -> dict:
        fn = _get(call, "function") or {}
        name = str(_get(fn, "name") or "")
        call_id = str(_get(call, "id") or "")
        raw_args = _get(fn, "arguments") or "{}"
        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
        except Exception:
            args = {}
        if name in BLOCKED_TOOLS:
            content = f"Error: tool '{name}' is not permitted for scheduled jobs"
        elif self._tools is None:
            content = "Error: no tool registry available"
        else:
            try:
                content = str(await self._tools.execute(name, **args))
            except Exception as e:
                logger.warning(f"scheduled tool {name} failed: {e}")
                content = f"Error: {e}"
        return {"role": "tool", "tool_call_id": call_id, "content": content}

    async def _call(self, client, kwargs: dict) -> Any:
        # Prefer async if client exposes it; else thread-pool sync call.
        if hasattr(client, "chat") and hasattr(client.chat, "completions") and \
           asyncio.iscoroutinefunction(getattr(client.chat.completions, "create", None)):
            return await client.chat.completions.create(**kwargs)
        # Sync client — run in executor to avoid blocking event loop.
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: client.chat.completions.create(**kwargs)
        )


def _system_message(allowed_tools: list[str]) -> str:
    if not allowed_tools:
        return (
            "You are a scheduled assistant with access to all available tools. "
            "Use them only when necessary. Be concise."
        )
    tool_list = ", ".join(allowed_tools)
    return (
        f"You are a scheduled assistant. You have access to these tools: {tool_list}. "
        "Use them only when necessary. Be concise."
    )


def _first_message(response: Any) -> Any:
    choices = _get(response, "choices") or []
    if not choices:
        return None
    return _get(choices[0], "message")


def _assistant_turn(message: Any, calls: list) -> dict:
    """Rebuild the assistant tool-call turn in wire format for the next call."""
    serialized = []
    for call in calls:
        fn = _get(call, "function") or {}
        serialized.append({
            "id": str(_get(call, "id") or ""),
            "type": "function",
            "function": {
                "name": str(_get(fn, "name") or ""),
                "arguments": _get(fn, "arguments") or "{}",
            },
        })
    return {
        "role": "assistant",
        "content": _get(message, "content") or "",
        "tool_calls": serialized,
    }


def _extract_text(response: Any) -> str:
    """Best-effort extract of assistant text from OpenAI-shaped response."""
    try:
        msg = _first_message(response)
        if msg is None:
            return ""
        content = _get(msg, "content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for p in content:
                if isinstance(p, dict) and p.get("type") == "text":
                    parts.append(p.get("text", ""))
            return "\n".join(parts)
        return str(content or "")
    except Exception:
        return ""
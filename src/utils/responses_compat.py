"""Conversions between OpenAI Chat shape and the OpenAI Responses API shape.

Pure functions — no SDK imports, no I/O. Testable in isolation. Used by
`llm_factory.chat_completion_responses` to route OpenAI-compatible clients
through the Responses API (`POST /v1/responses`) instead of
`chat.completions`, taking advantage of the server-side prompt cache
(`prompt_cache_key` + `prompt_cache_retention`).

Wire format reference (industry standard Responses API):
    request:
        model
        instructions        — system prompt (string)
        input               — string | array of input items
        temperature / top_p / max_output_tokens
        tools               — flat list, no {"type":"function"} envelope
        tool_choice         — "none" | "auto"
        stream
        prompt_cache_key    — server-side cache routing id
        prompt_cache_retention — "in-memory" (default) | "24h"
    response:
        id
        object: "response"
        status              — completed | incomplete | failed
        output              — array of {message | reasoning | function_call}
        output_text         — concatenated text (convenience)
        usage
        error               — only when status == "failed"
"""

from __future__ import annotations

import json
from typing import Any


# --- Request side ------------------------------------------------------------

def _flatten_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out: list[str] = []
        for p in content:
            if isinstance(p, dict):
                if p.get("type") == "text" and p.get("text"):
                    out.append(p["text"])
                elif p.get("type") == "image_url":
                    out.append("[image]")
            elif hasattr(p, "text"):
                out.append(p.text)
        return "\n".join(out)
    return ""


def _content_to_input_items(role: str, content: Any) -> list[dict]:
    """Translate an OpenAI message's content into Responses `input_item` shape.

    Strings → [{"type":"input_text","text":...}] for user, or
              [{"type":"output_text","text":...}] for assistant.
    Lists of parts (text / image_url) → preserved with their type tags.
    """
    if isinstance(content, str):
        text = content
        item_type = "output_text" if role == "assistant" else "input_text"
        return [{"type": item_type, "text": text}] if text else []

    out: list[dict] = []
    if not isinstance(content, list):
        return out
    for p in content:
        if not isinstance(p, dict):
            continue
        ptype = p.get("type")
        if ptype == "text":
            text = p.get("text", "")
            if not text:
                continue
            item_type = "output_text" if role == "assistant" else "input_text"
            out.append({"type": item_type, "text": text})
        elif ptype == "image_url":
            url_obj = p.get("image_url") or {}
            url = url_obj.get("url") if isinstance(url_obj, dict) else url_obj
            if url:
                out.append({"type": "input_image", "image_url": url})
    return out


def extract_system_prompt(messages: list[dict]) -> str:
    """Concatenate every leading `system` message's text. Stops at first
    non-system message so a stray system inserted mid-history is not promoted
    into the cacheable prefix."""
    parts: list[str] = []
    for m in messages or []:
        if m.get("role") != "system":
            break
        c = m.get("content")
        text = _flatten_text(c).strip() if c else ""
        if text:
            parts.append(text)
    return "\n\n".join(parts)


def messages_to_responses_input(messages: list[dict]) -> list[dict]:
    """Translate OpenAI Chat messages into Responses `input` array.

    System messages are excluded — caller passes them via `instructions`.
    Tool messages become `{type:"function_call_output", call_id, output}` items.
    Assistant tool_calls become separate `{type:"function_call"}` items
    alongside the assistant's text content.
    """
    out: list[dict] = []
    seen_non_system = False
    for m in messages or []:
        role = m.get("role")
        content = m.get("content", "")
        if role == "system":
            # Leading system blocks belong in `instructions` (caller extracts
            # via extract_system_prompt); silently drop them here so they
            # aren't duplicated. Mid-history system blocks (e.g. re-injected
            # after a tool round-trip) MUST be preserved as typed items, so
            # gate the drop on whether we've already seen a non-system item.
            if seen_non_system:
                # Always emit a typed message — empty text still surfaces as
                # `[{input_text,""}]` so the role remains visible to the API,
                # matching the empty-assistant guarantee.
                text = _flatten_text(content) or ""
                out.append({
                    "type": "message", "role": "system",
                    "content": [{"type": "input_text", "text": text}],
                })
            continue
        seen_non_system = True
        if role == "user":
            items = _content_to_input_items("user", content)
            if not items:
                items = [{"type": "input_text", "text": ""}]
            out.append({"type": "message", "role": "user", "content": items})
        elif role == "assistant":
            text_items = _content_to_input_items("assistant", content)
            tcs = m.get("tool_calls") or []
            # Tool calls first (Responses API expects them before the trailing
            # message for that assistant turn; ordering matters when the model
            # re-grounds to its own prior tool calls).
            for tc in tcs:
                fn = tc.get("function") or {}
                call_id = tc.get("id", "")
                name = fn.get("name", "")
                args_raw = fn.get("arguments", "{}")
                try:
                    args_obj = json.loads(args_raw) if isinstance(args_raw, str) else (args_raw or {})
                except json.JSONDecodeError:
                    args_obj = {}
                out.append({
                    "type": "function_call",
                    "call_id": call_id,
                    "name": name,
                    "arguments": json.dumps(args_obj, ensure_ascii=False),
                })
            if text_items:
                out.append({"type": "message", "role": "assistant", "content": text_items})
            elif not tcs:
                # Empty assistant turn (no content, no tool calls) — still emit
                # a typed message so the API doesn't reject on missing role.
                out.append({"type": "message", "role": "assistant",
                            "content": [{"type": "output_text", "text": ""}]})
        elif role == "tool":
            call_id = m.get("tool_call_id", "")
            out.append({
                "type": "function_call_output",
                "call_id": call_id,
                "output": _flatten_text(content),
            })
    return out


def tools_to_responses_tools(tools: list[dict] | None) -> list[dict] | None:
    """Translate OpenAI Chat tools into Responses-API flat tool list.

    OpenAI Chat:    [{"type":"function","function":{"name","description","parameters"}}]
    Responses API:  [{"type":"function","name","description","parameters"}]
    """
    if not tools:
        return None
    out: list[dict] = []
    for t in tools:
        if not isinstance(t, dict):
            continue
        if t.get("type") and t.get("type") != "function":
            out.append(t)
            continue
        fn = t.get("function") or {}
        name = fn.get("name") or t.get("name")
        if not name:
            continue
        out.append({
            "type": "function",
            "name": name,
            "description": fn.get("description", ""),
            "parameters": fn.get("parameters", {"type": "object", "properties": {}}),
        })
    return out or None


def tool_choice_responses(tool_choice: Any) -> Any:
    """Translate OpenAI Chat tool_choice → Responses-API tool_choice.

    Both APIs accept "none" / "auto" as strings; named-tool choices
    (`{"type":"function","function":{"name":...}}`) are translated to the
    Responses equivalent (`{"type":"function","name":...}`).
    """
    if tool_choice is None or tool_choice == "":
        return None
    if isinstance(tool_choice, str):
        return tool_choice
    if isinstance(tool_choice, dict):
        fn = tool_choice.get("function") or {}
        name = fn.get("name") or tool_choice.get("name")
        if name:
            return {"type": "function", "name": name}
        return None
    return None


def resolve_prompt_cache_retention(cache_retention: str, base_url: str = "") -> str | None:
    """Match openclaw's `getPromptCacheRetention` semantics.

    retention="long" + base_url contains "api.openai.com" → "24h"
    else → None (server default "in-memory")
    """
    if cache_retention != "long":
        return None
    return "24h" if "api.openai.com" in (base_url or "").lower() else None


def build_responses_kwargs(
    *,
    payload: dict,
    system_prompt: str,
    session_id: str | None,
    cache_retention: str,
    base_url: str,
) -> dict[str, Any]:
    """Build the kwargs dict for `client.responses.create(**kwargs)`.

    Drops chat-only fields (messages, stream) and replaces them with the
    Responses-API fields (input, instructions). Injects prompt_cache_key
    (when session_id is provided) and prompt_cache_retention (when long
    + api.openai.com).
    """
    model = payload.get("model", "")
    msgs = payload.get("messages") or []

    input_items = messages_to_responses_input(msgs)

    out: dict[str, Any] = {
        "model": model,
        "input": input_items,
    }
    if system_prompt:
        out["instructions"] = system_prompt

    if "temperature" in payload and payload["temperature"] is not None:
        out["temperature"] = payload["temperature"]
    if "top_p" in payload and payload["top_p"] is not None:
        out["top_p"] = payload["top_p"]
    if "max_tokens" in payload and payload["max_tokens"] is not None:
        out["max_output_tokens"] = payload["max_tokens"]
    if "max_output_tokens" in payload and payload["max_output_tokens"] is not None:
        out["max_output_tokens"] = payload["max_output_tokens"]

    tools = tools_to_responses_tools(payload.get("tools"))
    if tools:
        out["tools"] = tools
    tc = tool_choice_responses(payload.get("tool_choice"))
    if tc is not None:
        out["tool_choice"] = tc

    if session_id and cache_retention != "none":
        out["prompt_cache_key"] = session_id
    retention = resolve_prompt_cache_retention(cache_retention, base_url)
    if retention:
        out["prompt_cache_retention"] = retention

    return out


# --- Response side -----------------------------------------------------------

def _extract_text_from_output_item(item: dict) -> str:
    if not isinstance(item, dict):
        return ""
    if item.get("type") == "message":
        content = item.get("content") or []
        if isinstance(content, str):
            return content
        parts: list[str] = []
        for p in content:
            if isinstance(p, dict):
                if p.get("type") in ("output_text", "text") and p.get("text"):
                    parts.append(p["text"])
        return "\n".join(parts)
    if item.get("type") == "reasoning":
        summary = item.get("summary") or []
        parts = []
        for s in summary:
            if isinstance(s, dict) and s.get("text"):
                parts.append(s["text"])
        return "\n".join(parts)
    return ""


def _extract_function_calls_from_output(output: list[dict]) -> list[dict]:
    out: list[dict] = []
    for item in output or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "function_call":
            continue
        call_id = item.get("call_id", "") or item.get("id", "")
        name = item.get("name", "")
        args_raw = item.get("arguments", "{}")
        try:
            args_obj = json.loads(args_raw) if isinstance(args_raw, str) else (args_raw or {})
        except json.JSONDecodeError:
            args_obj = {}
        out.append({
            "id": call_id,
            "type": "function",
            "function": {
                "name": name,
                "arguments": json.dumps(args_obj, ensure_ascii=False),
            },
        })
    return out


def _map_finish_reason(status: str | None) -> str:
    if status == "incomplete":
        return "length"
    if status == "failed":
        return "stop"
    return "stop"


def responses_to_chat_shape(response: Any, model: str) -> dict:
    """Convert a Responses-API response (or its dict form) into the OpenAI
    Chat completions shape, so downstream code (and the L1/L2 cache hydrator)
    sees a uniform interface.

    Accepts either a SDK response object (with attribute access) or a plain
    dict — both shapes appear depending on whether the SDK decoded the
    response or the caller serialized it first.
    """
    def _get(obj, key, default=None):
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    rid = _get(response, "id", "responses") or "responses"
    rmodel = _get(response, "model", model) or model
    status = _get(response, "status", "completed")
    output = _get(response, "output", []) or []
    output_text = _get(response, "output_text", None)
    usage = _get(response, "usage", {}) or {}
    error = _get(response, "error", None)

    if isinstance(output_text, str) and output_text:
        text = output_text
    else:
        parts: list[str] = []
        for item in output:
            t = _extract_text_from_output_item(item if isinstance(item, dict) else {
                "type": getattr(item, "type", None),
                "content": getattr(item, "content", None),
                "summary": getattr(item, "summary", None),
            })
            if t:
                parts.append(t)
        text = "\n".join(parts)

    output_list: list[dict] = []
    for item in output:
        if isinstance(item, dict):
            output_list.append(item)
        else:
            output_list.append({
                "type": getattr(item, "type", None),
                "content": getattr(item, "content", None),
                "call_id": getattr(item, "call_id", None),
                "name": getattr(item, "name", None),
                "arguments": getattr(item, "arguments", None),
                "summary": getattr(item, "summary", None),
            })

    tool_calls = _extract_function_calls_from_output(output_list)
    finish_reason = _map_finish_reason(status)

    if error and not text and not tool_calls:
        err_msg = error.get("message") if isinstance(error, dict) else str(error)
        text = f"(Responses API error: {err_msg})"

    return {
        "id": rid,
        "model": rmodel,
        "choices": [{
            "index": 0,
            "finish_reason": finish_reason,
            "message": {
                "role": "assistant",
                "content": text,
                "tool_calls": tool_calls or None,
            },
        }],
        "usage": usage,
    }
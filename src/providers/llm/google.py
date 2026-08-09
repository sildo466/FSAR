# SPDX-License-Identifier: MIT
"""Gemini native REST chat completion translation and transport."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import httpx


GEMINI_DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
_FINISH_REASON_MAP = {
    "STOP": "stop",
    "MAX_TOKENS": "length",
    "SAFETY": "content_filter",
    "RECITATION": "content_filter",
    "OTHER": "stop",
}


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _parse_json_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {"_raw": value}


def _to_gemini_messages(messages: list[Any]) -> tuple[dict | None, list[dict]]:
    system_instruction: dict | None = None
    contents: list[dict] = []
    tool_names: dict[str, str] = {}

    for message in messages:
        role = _get(message, "role")
        if role == "system":
            text = _get(message, "content", "")
            if system_instruction is None:
                system_instruction = {"parts": [{"text": text}]}
            else:
                system_instruction["parts"].append({"text": text})
        elif role == "user":
            contents.append({"role": "user", "parts": [{"text": _get(message, "content", "")}]})
        elif role == "assistant":
            parts: list[dict] = []
            content_text = _get(message, "content", "") or ""
            if content_text:
                parts.append({"text": content_text})
            for tool_call in _get(message, "tool_calls", None) or []:
                function = _get(tool_call, "function", {}) or {}
                name = _get(function, "name", "")
                call_id = _get(tool_call, "id", "")
                if call_id:
                    tool_names[call_id] = name
                parts.append({
                    "functionCall": {
                        "name": name,
                        "args": _parse_json_value(_get(function, "arguments", "{}")),
                    }
                })
            contents.append({"role": "model", "parts": parts or [{"text": ""}]})
        elif role == "tool":
            call_id = _get(message, "tool_call_id", "")
            contents.append({
                "role": "user",
                "parts": [{
                    "functionResponse": {
                        "name": tool_names.get(call_id, "tool"),
                        "response": _parse_json_value(_get(message, "content", "{}")),
                    }
                }],
            })
    return system_instruction, contents


def _to_gemini_tools(tools: list[dict] | None) -> list[dict] | None:
    if not tools:
        return None
    declarations = []
    for tool in tools:
        function = tool.get("function", {})
        declarations.append({
            "name": function.get("name", ""),
            "description": function.get("description", ""),
            "parameters": function.get("parameters", {"type": "object", "properties": {}}),
        })
    return [{"functionDeclarations": declarations}]


def to_gemini_request(
    messages: list[dict],
    tools: list[dict] | None,
    thinking_payload: dict | None,
    max_tokens: int,
) -> dict:
    """Translate an OpenAI-style request into a Gemini request body."""
    system_instruction, contents = _to_gemini_messages(messages)
    body: dict[str, Any] = {"contents": contents}
    if system_instruction is not None:
        body["systemInstruction"] = system_instruction

    gemini_tools = _to_gemini_tools(tools)
    if gemini_tools:
        body["tools"] = gemini_tools

    generation_config: dict[str, Any] = {"maxOutputTokens": max_tokens}
    if thinking_payload and "generationConfig" in thinking_payload:
        generation_config.update(thinking_payload["generationConfig"])
    body["generationConfig"] = generation_config
    return body


def from_gemini_response(gemini_json: dict) -> dict:
    """Translate a Gemini response into an OpenAI-style message dictionary."""
    candidate = (gemini_json.get("candidates") or [{}])[0]
    parts = ((candidate.get("content") or {}).get("parts") or [])
    content_texts: list[str] = []
    reasoning_texts: list[str] = []
    tool_calls: list[dict] = []
    for part in parts:
        if "text" in part:
            target = reasoning_texts if part.get("thought") is True else content_texts
            target.append(part["text"])
        if "functionCall" in part:
            function_call = part["functionCall"]
            tool_calls.append({
                "id": f"gemini-{uuid.uuid4().hex[:8]}",
                "type": "function",
                "function": {
                    "name": function_call.get("name", ""),
                    "arguments": json.dumps(function_call.get("args") or {}, ensure_ascii=False),
                },
            })
    finish_reason = _FINISH_REASON_MAP.get(candidate.get("finishReason", "STOP"), "stop")
    return {
        "content": "".join(content_texts),
        "reasoning_content": "".join(reasoning_texts),
        "tool_calls": tool_calls,
        "finish_reason": finish_reason,
        "usage": gemini_json.get("usageMetadata") or {},
    }


_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _build_url(model: str, api_key: str, stream: bool) -> str:
    action = "streamGenerateContent" if stream else "generateContent"
    suffix = f"?alt=sse&key={api_key}" if stream else f"?key={api_key}"
    return f"{GEMINI_DEFAULT_BASE_URL}/models/{model}:{action}{suffix}"


def _is_retryable(response: httpx.Response) -> bool:
    return response.status_code in _RETRYABLE_STATUS


async def _post_with_retry(
    client: httpx.AsyncClient,
    url: str,
    body: dict,
) -> httpx.Response:
    response = await client.post(url, json=body, timeout=60.0)
    if _is_retryable(response):
        await asyncio.sleep(0.5)
        response = await client.post(url, json=body, timeout=60.0)
    response.raise_for_status()
    return response


async def _send_stream_with_retry(
    client: httpx.AsyncClient,
    url: str,
    body: dict,
) -> httpx.Response:
    request = client.build_request("POST", url, json=body, timeout=60.0)
    response = await client.send(request, stream=True)
    if _is_retryable(response):
        await response.aclose()
        await asyncio.sleep(0.5)
        request = client.build_request("POST", url, json=body, timeout=60.0)
        response = await client.send(request, stream=True)
    try:
        response.raise_for_status()
    except Exception:
        await response.aclose()
        raise
    return response


async def _google_nonstream_completion(
    *,
    api_key: str,
    model: str,
    messages: list[dict],
    tools: list[dict] | None,
    thinking_payload: dict | None,
    max_tokens: int,
) -> dict:
    body = to_gemini_request(messages, tools, thinking_payload, max_tokens)
    url = _build_url(model, api_key, stream=False)
    async with httpx.AsyncClient() as client:
        response = await _post_with_retry(client, url, body)
    return from_gemini_response(response.json())


async def _iter_gemini_sse(response: httpx.Response):
    async for raw_line in response.aiter_lines():
        line = raw_line.strip()
        if not line or line.startswith(":") or not line.startswith("data:"):
            continue
        payload = line[len("data:"):].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            yield json.loads(payload)
        except json.JSONDecodeError:
            continue


async def _stream_chunks(response: httpx.Response):
    tool_calls: list[dict] = []
    async for event in _iter_gemini_sse(response):
        candidate = (event.get("candidates") or [{}])[0]
        parts = ((candidate.get("content") or {}).get("parts") or [])
        for part in parts:
            text = part.get("text")
            if text:
                if part.get("thought") is True:
                    yield {"delta": "", "thinking": text}
                else:
                    yield {"delta": text, "thinking": ""}
            if "functionCall" in part:
                function_call = part["functionCall"]
                tool_calls.append({
                    "id": f"gemini-{uuid.uuid4().hex[:8]}",
                    "type": "function",
                    "function": {
                        "name": function_call.get("name", ""),
                        "arguments": json.dumps(function_call.get("args") or {}, ensure_ascii=False),
                    },
                })
        if candidate.get("finishReason") or event.get("finishReason"):
            if tool_calls:
                yield {"delta": "", "thinking": "", "tool_calls": tool_calls}
            yield {"delta": "", "thinking": "", "done": True}
            return
    if tool_calls:
        yield {"delta": "", "thinking": "", "tool_calls": tool_calls}
    yield {"delta": "", "thinking": "", "done": True}


async def _google_stream_completion(
    *,
    api_key: str,
    model: str,
    messages: list[dict],
    tools: list[dict] | None,
    thinking_payload: dict | None,
    max_tokens: int,
):
    body = to_gemini_request(messages, tools, thinking_payload, max_tokens)
    url = _build_url(model, api_key, stream=True)
    async with httpx.AsyncClient() as client:
        response = await _send_stream_with_retry(client, url, body)
        try:
            async for chunk in _stream_chunks(response):
                yield chunk
        finally:
            await response.aclose()


def google_chat_completion(
    *,
    api_key: str,
    model: str,
    messages: list[dict],
    tools: list[dict] | None,
    thinking_payload: dict | None,
    max_tokens: int,
    stream: bool = False,
) -> Any:
    """Return an awaitable completion or, when streaming, an async iterator."""
    if stream:
        return _google_stream_completion(
            api_key=api_key,
            model=model,
            messages=messages,
            tools=tools,
            thinking_payload=thinking_payload,
            max_tokens=max_tokens,
        )
    return _google_nonstream_completion(
        api_key=api_key,
        model=model,
        messages=messages,
        tools=tools,
        thinking_payload=thinking_payload,
        max_tokens=max_tokens,
    )

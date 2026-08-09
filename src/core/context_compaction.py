# SPDX-License-Identifier: MIT
"""Structure-aware context checkpoints for long-running agent tasks."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any


CHECKPOINT_MARKER = "[FSAR EXECUTION CHECKPOINT]"
CHECKPOINT_NAME = "fsar_context_checkpoint"
MAX_TOOL_RESULT_CHARS = 12_000
MAX_SUMMARY_MESSAGE_CHARS = 48_000

Summarizer = Callable[[list[dict[str, str]], str | None], Awaitable[str]]


def estimate_text_tokens(text: object) -> int:
    value = str(text or "")
    ascii_chars = sum(1 for char in value if ord(char) < 128)
    return max(1, ascii_chars // 4 + (len(value) - ascii_chars))


def message_cost(message: Any) -> int:
    content = _get(message, "content", "")
    tool_calls = _get(message, "tool_calls", None)
    return estimate_text_tokens(content) + estimate_text_tokens(tool_calls) + 8


def context_cost(messages: list[Any]) -> int:
    return sum(message_cost(message) for message in messages)


async def compact_context(
    messages: list[Any],
    *,
    context_window: int,
    max_output: int,
    threshold: float,
    summarize: Summarizer,
) -> tuple[list[Any], bool]:
    trigger = max(1, int(context_window * threshold) - max_output)
    if len(messages) < 5 or context_cost(messages) <= trigger:
        return messages, False

    system = messages[0]
    groups = _message_groups(messages[1:])
    if len(groups) < 3:
        return messages, False

    keep_budget = max(max_output * 2, int(context_window * 0.30))
    kept: list[list[Any]] = []
    kept_cost = 0
    while groups and (kept_cost < keep_budget or len(kept) < 4):
        group = groups.pop()
        kept.insert(0, group)
        kept_cost += sum(message_cost(message) for message in group)

    if not groups:
        return messages, False

    old_messages = [message for group in groups for message in group]
    previous_summary = _extract_previous_checkpoint(old_messages)
    old_messages = [
        message for message in old_messages if not _is_checkpoint(message)
    ]
    if not old_messages:
        return messages, False

    chunks = _summary_chunks(
        old_messages,
        max_tokens=max(512, int(context_window * 0.35)),
    )
    summary = previous_summary
    try:
        for chunk in chunks:
            summary = (await summarize(_safe_transcript(chunk), summary)).strip()
            if not summary:
                raise ValueError("empty context checkpoint")
    except Exception:
        return messages, False

    checkpoint = {
        "role": "system",
        "name": CHECKPOINT_NAME,
        "content": f"{CHECKPOINT_MARKER}\n{summary}",
    }
    tail = [message for group in kept for message in group]
    return [system, checkpoint, *tail], True


def _message_groups(messages: list[Any]) -> list[list[Any]]:
    groups: list[list[Any]] = []
    index = 0
    while index < len(messages):
        message = messages[index]
        group = [message]
        index += 1
        if _get(message, "role", "") == "assistant" and _get(
            message, "tool_calls", None
        ):
            while index < len(messages) and _get(messages[index], "role", "") == "tool":
                group.append(messages[index])
                index += 1
        groups.append(group)
    return groups


def _summary_chunks(messages: list[Any], *, max_tokens: int) -> list[list[Any]]:
    groups = _message_groups(messages)
    chunks: list[list[Any]] = []
    current: list[Any] = []
    current_cost = 0
    for group in groups:
        cost = sum(message_cost(message) for message in group)
        if current and current_cost + cost > max_tokens:
            chunks.append(current)
            current = []
            current_cost = 0
        current.extend(group)
        current_cost += cost
    if current:
        chunks.append(current)
    return chunks


def _safe_transcript(messages: list[Any]) -> list[dict[str, str]]:
    transcript: list[dict[str, str]] = []
    for message in messages:
        role = str(_get(message, "role", "unknown") or "unknown")
        content = _get(message, "content", "")
        if not isinstance(content, str):
            try:
                content = json.dumps(content, ensure_ascii=False, default=str)
            except Exception:
                content = str(content)
        limit = MAX_TOOL_RESULT_CHARS if role == "tool" else MAX_SUMMARY_MESSAGE_CHARS
        if len(content) > limit:
            half = limit // 2
            removed = len(content) - limit
            content = (
                f"{content[:half]}\n[... {removed} message characters omitted ...]\n"
                f"{content[-half:]}"
            )
        tool_calls = _get(message, "tool_calls", None)
        if tool_calls:
            content = f"{content}\nTool calls: {tool_calls}"
        transcript.append({"role": role, "content": content})
    return transcript


def _extract_previous_checkpoint(messages: list[Any]) -> str | None:
    for message in reversed(messages):
        if not _is_checkpoint(message):
            continue
        content = str(_get(message, "content", ""))
        return content.removeprefix(CHECKPOINT_MARKER).strip()
    return None


def _is_checkpoint(message: Any) -> bool:
    return (
        _get(message, "name", "") == CHECKPOINT_NAME
        or str(_get(message, "content", "")).startswith(CHECKPOINT_MARKER)
    )


def _get(message: Any, key: str, default: Any) -> Any:
    if isinstance(message, dict):
        return message.get(key, default)
    return getattr(message, key, default)

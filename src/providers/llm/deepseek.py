"""DeepSeek-specific request/response handling.

DeepSeek's chat API is OpenAI-compatible but has two divergences that break
tool-call multi-turn flows unless we adapt the request:

1. Thinking mode (default ON) returns ``reasoning_content`` on the assistant
   message. When the assistant turn includes a tool call, the API requires
   ``reasoning_content`` to be echoed back in every subsequent user turn;
   otherwise the call returns HTTP 400.
2. Thinking is toggled via ``extra_body={"thinking": {"type": "enabled"}}``
   on the request, not via a top-level OpenAI parameter.

The OpenAI Python SDK preserves ``reasoning_content`` on a
``ChatCompletionMessage`` when you re-send the same object, but the project
serialises the message to a dict at the message-append boundary; this module
restores the field at that boundary and injects the ``extra_body`` at the
call site.
"""
from __future__ import annotations

from typing import Any, Iterable
from urllib.parse import urlparse

_DEEPSEEK_OFFICIAL_HOSTS = {
    "api.deepseek.com",
}


def is_deepseek_official(base_url: str) -> bool:
    """Return True if base_url points at DeepSeek's first-party API."""
    if not base_url:
        return False
    try:
        host = (urlparse(base_url).hostname or "").lower()
    except ValueError:
        return False
    return host in _DEEPSEEK_OFFICIAL_HOSTS


def extra_body_for_thinking() -> dict[str, Any]:
    return {"thinking": {"type": "enabled"}}


def _message_to_dict(message: Any) -> dict[str, Any]:
    if isinstance(message, dict):
        return dict(message)
    if hasattr(message, "model_dump"):
        return message.model_dump(exclude_unset=False)
    if hasattr(message, "to_dict"):
        return message.to_dict()
    if hasattr(message, "__dict__"):
        return {k: v for k, v in message.__dict__.items() if not k.startswith("_")}
    return dict(message)


def prepare_messages(messages: Iterable[Any]) -> list[dict[str, Any]]:
    """Coerce messages to dicts and preserve ``reasoning_content``.

    The OpenAI SDK's default model_dump already keeps ``reasoning_content``,
    but this guard makes the behaviour explicit and resilient if upstream
    code ever swaps the SDK.
    """
    out: list[dict[str, Any]] = []
    for m in messages:
        d = _message_to_dict(m)
        reasoning = getattr(m, "reasoning_content", None) if not isinstance(m, dict) else d.get("reasoning_content")
        if reasoning and "reasoning_content" not in d:
            d["reasoning_content"] = reasoning
        out.append(d)
    return out

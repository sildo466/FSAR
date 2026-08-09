"""Anthropic prompt-cache payload builder + break-tracking log.

- `cache_control: {type:"ephemeral"}` rewriting on the last system block +
  the trailing user turn.
- Per-session timestamp log for cache-break observability (Anthropic manages
  cache invalidation server-side, so there is no POST/PATCH client lifecycle
  to drive — the SDK just sends the markers and the server decides).

Endpoints where `ttl: "1h"` is honoured:
- anthropic.com direct
- anthropic on Vertex AI (modelApi="anthropic-messages" with vertexai base_url)
- custom relays that forward the `ttl` field

For other relays (Amazon Bedrock, OpenRouter Anthropic passthrough), the SDK
strips unknown `ttl` values silently — so we only attach `ttl: "1h"` when the
provider is known to support it, matching the `isLongTtlEligibleEndpoint`
heuristic.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Iterable, Optional


def digest_system_prompt(system_prompt: str) -> str:
    return hashlib.sha256((system_prompt or "").encode("utf-8")).hexdigest()


def is_long_ttl_eligible(base_url: str, provider_override: Optional[str] = None) -> bool:
    """Match the `isLongTtlEligibleEndpoint` semantics.

    Eligible: anthropic.com, anthropic on vertexai, and explicit provider
    override. Ineligible: bedrock, openrouter passthrough, anything else.
    """
    if provider_override == "anthropic":
        return True
    if not base_url:
        return False
    u = base_url.lower()
    if "anthropic.com" in u:
        return True
    if "anthropic" in u and "vertexai" in u:
        return True
    if "-aiplatform.googleapis.com" in u:
        # Vertex AI — eligible only when caller says so via override (because
        # project/location must be configured separately on the SDK).
        return provider_override == "anthropic"
    return False


def resolve_cache_control(
    *,
    cache_retention: str,
    base_url: str = "",
    provider_override: Optional[str] = None,
) -> Optional[dict]:
    """Return the cache_control marker to attach, or None if retention=none."""
    if cache_retention == "none":
        return None
    if cache_retention == "long" and is_long_ttl_eligible(base_url, provider_override):
        return {"type": "ephemeral", "ttl": "1h"}
    return {"type": "ephemeral"}


def _flatten_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for p in content:
            if isinstance(p, dict):
                if p.get("type") == "text" and p.get("text"):
                    parts.append(p["text"])
                elif p.get("type") == "image_url":
                    parts.append("[image]")
            elif hasattr(p, "text"):
                parts.append(p.text)
        return "\n".join(parts)
    return ""


def build_system_block(
    text: str,
    cache_control: Optional[dict],
) -> dict:
    """Anthropic system message block — a single block carrying the merged
    system prompt + optional cache_control marker."""
    block: dict[str, Any] = {"type": "text", "text": text}
    if cache_control:
        block["cache_control"] = cache_control
    return block


def convert_messages_to_anthropic(
    messages: list[dict],
    cache_control: Optional[dict],
) -> tuple[Optional[list[dict]], list[dict]]:
    """Convert OpenAI-shaped messages into (system_blocks, messages_for_anthropic).

    - System messages are stripped out and concatenated into the system param.
    - The last user message's last text block gets cache_control if provided.
    - Tool messages become user-role blocks with a tool_result content block.
    - Assistant tool_calls become assistant content blocks of type tool_use.
    """
    system_parts: list[str] = []
    anthropic_messages: list[dict] = []
    for m in messages or []:
        role = m.get("role")
        content = m.get("content", "")
        if role == "system":
            sys_text = _flatten_text(content)
            if sys_text and sys_text.strip():
                system_parts.append(sys_text)
            continue
        if role == "user":
            text = _flatten_text(content)
            anthropic_messages.append({"role": "user", "content": text})
        elif role == "assistant":
            text = _flatten_text(content)
            blocks: list[dict] = []
            if text:
                blocks.append({"type": "text", "text": text})
            for tc in m.get("tool_calls") or []:
                fn = tc.get("function") or {}
                args_raw = fn.get("arguments", "{}")
                try:
                    args_obj = json.loads(args_raw) if isinstance(args_raw, str) else (args_raw or {})
                except json.JSONDecodeError:
                    args_obj = {}
                blocks.append({
                    "type": "tool_use",
                    "id": tc.get("id", ""),
                    "name": fn.get("name", ""),
                    "input": args_obj,
                })
            if not blocks:
                blocks.append({"type": "text", "text": ""})
            anthropic_messages.append({"role": "assistant", "content": blocks})
        elif role == "tool":
            anthropic_messages.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": m.get("tool_call_id", ""),
                    "content": _flatten_text(content),
                }],
            })

    system_blocks: Optional[list[dict]] = None
    if system_parts:
        joined = "\n\n".join(system_parts)
        system_blocks = [build_system_block(joined, cache_control)]

    if anthropic_messages and cache_control and anthropic_messages[-1]["role"] == "user":
        last = anthropic_messages[-1]
        if isinstance(last["content"], str):
            # Convert trailing user string into a single text block carrying
            # the cache_control marker.
            last["content"] = [{"type": "text", "text": last["content"], "cache_control": cache_control}]
        elif isinstance(last["content"], list):
            # Already a list (e.g. tool_result) — append a leading text block.
            last["content"] = [{"type": "text", "text": "", "cache_control": cache_control}] + list(last["content"])

    return system_blocks, anthropic_messages


def convert_tools_to_anthropic(tools: Optional[list[dict]]) -> Optional[list[dict]]:
    """OpenAI tools → Anthropic tools.

    OpenAI shape: {"type": "function", "function": {"name", "description", "parameters"}}
    Anthropic shape: {"name", "description", "input_schema"}
    """
    if not tools:
        return None
    out: list[dict] = []
    for t in tools:
        if not isinstance(t, dict):
            continue
        fn = t.get("function") or t
        name = fn.get("name")
        if not name:
            continue
        out.append({
            "name": name,
            "description": fn.get("description", ""),
            "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
        })
    return out or None


def anthropic_response_to_openai_shape(
    response: Any,
    model: str,
) -> dict:
    """Normalize `anthropic.Anthropic.messages.create(...)` output into the
    OpenAI chat.completions shape so downstream call sites (and the L1/L2
    cache hydrator) see a uniform interface."""
    content_blocks = getattr(response, "content", None) or []
    text_parts: list[str] = []
    tool_calls: list[dict] = []
    for i, block in enumerate(content_blocks):
        btype = getattr(block, "type", None) or (block.get("type") if isinstance(block, dict) else None)
        if btype == "text":
            txt = getattr(block, "text", "") or (block.get("text", "") if isinstance(block, dict) else "")
            text_parts.append(txt)
        elif btype == "tool_use":
            name = getattr(block, "name", "") or (block.get("name", "") if isinstance(block, dict) else "")
            args_obj = getattr(block, "input", {}) if not isinstance(block, dict) else (block.get("input", {}) or {})
            block_id = getattr(block, "id", "") or (block.get("id", "") if isinstance(block, dict) else "")
            tool_calls.append({
                "id": block_id,
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": json.dumps(args_obj, ensure_ascii=False),
                },
            })

    return {
        "id": getattr(response, "id", "") or "anthropic",
        "model": getattr(response, "model", "") or model,
        "choices": [{
            "index": 0,
            "finish_reason": getattr(response, "stop_reason", None) or "stop",
            "message": {
                "role": "assistant",
                "content": "\n".join([t for t in text_parts if t]),
                "tool_calls": tool_calls or None,
            },
        }],
        "usage": {},
    }


# --- Cache-TTL observability log ---------------------------------------------

class AnthropicCacheLog:
    """Append-only timestamp log for cache-break observability.

    Each record is tagged with (timestamp, provider, modelId). The `last` log
    is used by observability tooling to compare cache-read drop deltas;
    fsar doesn't yet have a UI for this, but downstream reflection code can.
    """

    def __init__(self, db_path: str | Path = "data/llm_cache.db"):
        self._db_path = str(db_path)
        self._lock = threading.Lock()
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS anthropic_cache_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    provider TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    cache_retention TEXT NOT NULL,
                    system_prompt_digest TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def append(
        self,
        *,
        provider: str,
        model_id: str,
        cache_retention: str,
        system_prompt: str,
        now: Optional[float] = None,
    ) -> None:
        try:
            with self._lock, sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    """INSERT INTO anthropic_cache_log
                       (timestamp, provider, model_id, cache_retention,
                        system_prompt_digest)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        now if now is not None else time.time(),
                        provider,
                        model_id,
                        cache_retention,
                        digest_system_prompt(system_prompt),
                    ),
                )
                conn.commit()
        except Exception:
            pass

    def last_for(
        self,
        *,
        provider: str,
        model_id: str,
    ) -> Optional[float]:
        try:
            with self._lock, sqlite3.connect(self._db_path) as conn:
                cur = conn.execute(
                    """SELECT timestamp FROM anthropic_cache_log
                       WHERE provider = ? AND model_id = ?
                       ORDER BY id DESC LIMIT 1""",
                    (provider, model_id),
                )
                row = cur.fetchone()
            return float(row[0]) if row else None
        except Exception:
            return None

    def stats(self) -> dict:
        try:
            with self._lock, sqlite3.connect(self._db_path) as conn:
                cur = conn.execute("SELECT COUNT(*) FROM anthropic_cache_log")
                (n,) = cur.fetchone()
            return {"rows": int(n)}
        except Exception:
            return {"rows": 0}


_DEFAULT_LOG: Optional[AnthropicCacheLog] = None
_DEFAULT_LOG_LOCK = threading.Lock()


def get_default_anthropic_cache_log() -> AnthropicCacheLog:
    global _DEFAULT_LOG
    if _DEFAULT_LOG is None:
        with _DEFAULT_LOG_LOCK:
            if _DEFAULT_LOG is None:
                from src.utils.config import get_config
                _DEFAULT_LOG = AnthropicCacheLog(db_path=get_config().llm_cache_db_path)
    return _DEFAULT_LOG

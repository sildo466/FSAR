"""Shared LLM client factory with cache interception + provider cache markers.

Wraps the OpenAI Python SDK so every `chat.completions.create` call site
benefits from the L1+L2 cache without each site having to know about it.

Provider cache marker hooks (analogous to openclaw's
`anthropic-cache-control-payload.ts`):
- anthropic: emits `cache_control: {type: "ephemeral", ttl: "1h"}` on the last
  system block + last user turn (only if the requesting provider family is
  Anthropic or a compatible relay like Amazon Bedrock with anthropic model id).
- gemini: emits a stub `cached_content` placeholder via extra_body (no real
  Gemini SDK installed by default; a real hook would call the cachedContents
  API in the style of openclaw's `google-prompt-cache.ts`).
- openai: most OpenAI-compatible providers don't support prompt cache markers
  natively, so we fall back to disk-level response cache only. A few providers
  accept `prompt_cache_key`; we attach it when detected.

Current fsar uses a single OpenAI-compatible provider (MiniMax-M3). The hooks
are no-ops for that provider today but available the moment a different
provider is configured.

Public surface:
- make_llm_client(provider_id: str) -> OpenAI-compatible client
- cached_chat_completion(client, **kwargs) -> OpenAI-compatible response
  (drop-in replacement for `client.chat.completions.create(**kwargs)`)
- detect_provider_family(model, base_url) -> "anthropic" | "gemini" | "openai"
- apply_provider_cache_markers(messages, **kwargs) -> updated messages + kwargs
"""

from __future__ import annotations

import copy
import ssl
from typing import Any, Optional

import httpx
from openai import OpenAI

from src.utils.config import get_config
from src.utils.llm_cache import LLMCache, get_default_cache, make_cache_key
from src.utils.logger import logger


_CLIENTS: dict[str, OpenAI] = {}
_GEMINI_CLIENTS: dict[str, Any] = {}
_ANTHROPIC_CLIENTS: dict[str, Any] = {}
_FACTORY_LOCK = __import__("threading").Lock()


def detect_provider_family(model: str = "", base_url: str = "") -> str:
    """Best-effort provider family detection.

    Inspects (in order): explicit `provider` env/settings, model id prefix,
    base URL host substring. Defaults to "openai".
    """
    from src.utils.config import get_config

    cfg = get_config()
    explicit = (cfg.get("llm.cache.provider_override") or "").strip().lower()
    if explicit in {"anthropic", "gemini", "openai"}:
        return explicit
    m = (model or "").lower()
    if m.startswith(("claude", "anthropic")) or m.startswith(("models/claude", "models/anthropic")):
        return "anthropic"
    if (
        m.startswith(("gemini", "google/"))
        or "/gemini" in m
        or m.startswith("models/gemini")
    ):
        return "gemini"
    if "anthropic" in (base_url or "").lower():
        return "anthropic"
    if "generativelanguage" in (base_url or "").lower():
        return "gemini"
    return "openai"


def resolve_anthropic_cache_marker(
    cache_retention: str,
    base_url: str = "",
    provider_override: str = "",
) -> Optional[dict]:
    """Resolve the cache_control marker; thin pass-through to anthropic_cache."""
    from src.utils.anthropic_cache import resolve_cache_control
    return resolve_cache_control(
        cache_retention=cache_retention,
        base_url=base_url,
        provider_override=provider_override or None,
    )


def apply_provider_cache_markers(
    messages: list[dict],
    *,
    model: str = "",
    base_url: str = "",
    cache_retention: str = "short",
    extra_body: Optional[dict] = None,
) -> tuple[list[dict], dict, Optional[dict]]:
    """Mutate (in a copy) messages + kwargs to inject provider-specific cache
    markers. Returns (messages, kwargs, extra_body).

    `cache_retention` ∈ {"none", "short", "long"}. "none" disables markers.
    """
    msgs = copy.deepcopy(messages)
    body = dict(extra_body or {})
    if cache_retention == "none":
        return msgs, {}, body

    family = detect_provider_family(model, base_url)
    if family == "anthropic":
        ttl = "1h" if cache_retention == "long" else None
        marker = {"type": "ephemeral"}
        if ttl:
            marker["ttl"] = ttl
        if msgs and msgs[0].get("role") == "system":
            head = msgs[0]
            tail = msgs[-1]
            head["cache_control"] = marker
            if tail is not head:
                tail["cache_control"] = marker
    elif family == "anthropic":
        # Anthropic chat path runs convert_messages_to_anthropic() — it injects
        # cache_control markers into the Anthropic-shaped payload directly, so
        # there's nothing to do here on the OpenAI-shape messages.
        pass
    elif family == "gemini":
        # Gemini-side prompt cache reference. Returned in `body` so the
        # caller (cached_chat_completion → chat_completion_gemini) can pull it
        # out and inject into GenerateContentConfig.cached_content.
        # The actual POST/PATCH against the cachedContents API lives in
        # src/utils/gemini_cache.py — keeping marker resolution pure.
        body.setdefault("cached_content", "")
    else:
        # OpenAI-compatible: a few relays accept prompt_cache_key for sticky
        # routing — only set it when caller opted in (caller decides via
        # cache_retention == "long").
        if cache_retention == "long":
            body.setdefault("prompt_cache_key", _derive_cache_key(model, msgs))

    return msgs, {}, body


def _derive_cache_key(model: str, messages: list[dict]) -> str:
    import hashlib

    from src.utils.llm_cache import stable_dumps

    return hashlib.sha256(stable_dumps({"model": model, "messages": messages}).encode("utf-8")).hexdigest()[:32]


def make_llm_client(provider_id: str) -> OpenAI:
    """Return a singleton OpenAI client for the named provider.

    All call sites that need an LLM should use this instead of constructing
    `OpenAI(...)` themselves, so cache wiring is uniform.
    """
    if provider_id in _CLIENTS:
        return _CLIENTS[provider_id]
    with _FACTORY_LOCK:
        if provider_id in _CLIENTS:
            return _CLIENTS[provider_id]
        cfg = get_config().get_llm_config(provider_id)
        ctx = ssl.create_default_context()
        try:
            client = OpenAI(
                api_key=cfg.get("api_key", ""),
                base_url=cfg.get("base_url", ""),
                http_client=httpx.Client(verify=ctx),
            )
        except TypeError:
            # OpenAI SDK < 1.0 or custom subclasses: fall back without http_client.
            client = OpenAI(
                api_key=cfg.get("api_key", ""),
                base_url=cfg.get("base_url", ""),
            )
        _CLIENTS[provider_id] = client
        return client


def cached_chat_completion(
    client: OpenAI,
    *,
    cache: Optional[LLMCache] = None,
    cache_enabled: Optional[bool] = None,
    cache_retention: Optional[str] = None,
    **kwargs: Any,
) -> Any:
    """Drop-in replacement for `client.chat.completions.create(**kwargs)`.

    On hit, returns the cached response (re-hydrated if necessary).
    On miss, calls the real API and writes the response into the cache.

    Streaming (`stream=True`) is passed straight through to the real call —
    a streamed response cannot be losslessly cached.

    When the configured provider is Gemini, the call is dispatched to
    `chat_completion_gemini` instead so the official `google.genai` SDK is
    used (which is required for cachedContent injection).
    """
    cfg = get_config()
    cache = cache if cache is not None else get_default_cache()
    if cache_enabled is None:
        cache_enabled = cfg.llm_cache_enabled and not kwargs.get("stream", False)
    retention = cache_retention or cfg.llm_cache_retention

    base_url = ""
    try:
        base_url = str(getattr(client, "base_url", "") or "")
    except Exception:
        base_url = ""

    payload: dict = dict(kwargs)
    if not payload.get("model"):
        raise ValueError("model must be supplied to cached_chat_completion")

    msgs = payload.get("messages") or []
    family = detect_provider_family(str(payload.get("model", "")), base_url)

    # Provider cache marker injection (Anthropic cache_control / Gemini cached_content stub).
    body_out: dict = {}
    if msgs:
        msgs_out, _, body = apply_provider_cache_markers(
            msgs,
            model=str(payload.get("model", "")),
            base_url=base_url,
            cache_retention=retention,
        )
        payload["messages"] = msgs_out
        body_out = body or {}

    if family == "gemini" and not payload.get("stream"):
        return chat_completion_gemini(
            messages=payload["messages"],
            model=str(payload.get("model", "")),
            cache=cache,
            cache_enabled=cache_enabled,
            cache_retention=retention,
            base_url=base_url,
            extra_body=body_out,
            payload=payload,
            tools=payload.get("tools"),
            tool_choice=payload.get("tool_choice"),
            max_tokens=payload.get("max_tokens"),
            temperature=payload.get("temperature"),
        )

    if family == "anthropic" and not payload.get("stream"):
        return chat_completion_anthropic(
            messages=payload["messages"],
            model=str(payload.get("model", "")),
            cache=cache,
            cache_enabled=cache_enabled,
            cache_retention=retention,
            base_url=base_url,
            payload=payload,
            tools=payload.get("tools"),
            max_tokens=payload.get("max_tokens") or 4096,
            temperature=payload.get("temperature"),
        )

    if (
        family == "openai"
        and cfg.llm_cache_use_responses_api
        and not payload.get("stream")
        and not kwargs.get("_skip_responses_dispatch", False)
    ):
        return chat_completion_responses(
            client,
            cache=cache,
            cache_enabled=cache_enabled,
            cache_retention=retention,
            base_url=base_url,
            **{k: v for k, v in kwargs.items() if k != "_skip_responses_dispatch"},
        )

    if cache_enabled and not payload.get("stream"):
        try:
            cached = cache.get(payload)
            if cached is not None:
                logger.debug(f"LLM cache hit (key={make_cache_key(payload)[:12]}…)")
                return _rehydrate_response(cached)
        except Exception:
            pass

    chat = client.chat.completions
    create = chat.create
    response = create(**payload)

    if cache_enabled and not payload.get("stream"):
        try:
            cache.put(payload, response, cache_enabled=True)
        except Exception:
            pass
    return response


# --- Gemini-native path -------------------------------------------------------

_GEMINI_LOCK = __import__("threading").Lock()


def make_gemini_client(provider_id: str):
    """Singleton `google.genai.Client` for the named provider."""
    if provider_id in _GEMINI_CLIENTS:
        return _GEMINI_CLIENTS[provider_id]
    with _GEMINI_LOCK:
        if provider_id in _GEMINI_CLIENTS:
            return _GEMINI_CLIENTS[provider_id]
        cfg = get_config().get_llm_config(provider_id)
        api_key = cfg.get("api_key", "")
        base_url = cfg.get("base_url", "") or None
        try:
            from google import genai  # type: ignore

            kwargs: dict[str, Any] = {"api_key": api_key}
            if base_url:
                try:
                    from google.genai import types as _t  # type: ignore

                    kwargs["http_options"] = _t.HttpOptions(base_url=base_url)
                except Exception:
                    pass
            client = genai.Client(**kwargs)
        except Exception:
            client = None
        _GEMINI_CLIENTS[provider_id] = client
        return client


def _extract_system_prompt(messages: list[dict]) -> Optional[str]:
    """Concatenate every leading `system` message's text content. Stops at the
    first non-system message so a stray system inserted mid-history doesn't get
    promoted into the cacheable prefix.
    """
    parts: list[str] = []
    for m in messages:
        if m.get("role") != "system":
            break
        c = m.get("content")
        if isinstance(c, str) and c.strip():
            parts.append(c)
        elif isinstance(c, list):
            for p in c:
                if isinstance(p, dict) and p.get("type") == "text" and p.get("text"):
                    parts.append(p["text"])
    return "\n\n".join(parts) if parts else None


def chat_completion_gemini(
    *,
    messages: list[dict],
    model: str,
    cache: Optional[LLMCache] = None,
    cache_enabled: bool = True,
    cache_retention: str = "short",
    base_url: str = "",
    extra_body: Optional[dict] = None,
    payload: Optional[dict] = None,
    tools: Any = None,
    tool_choice: Any = None,
    max_tokens: Any = None,
    temperature: Any = None,
) -> Any:
    """Drop-in for OpenAI chat.completions when provider=gemini.

    Routes through `google.genai.Client.models.generate_content`. The
    stable prefix is extracted as the leading system prompt(s) and a
    cachedContent reference is requested via GeminiPromptCache.
    """
    from src.utils.gemini_cache import GeminiPromptCache, get_default_gemini_cache

    payload = payload if payload is not None else {"model": model, "messages": messages}
    cache_key_payload = dict(payload)
    cache_key_payload.setdefault("provider", "google")
    cache_key_payload.setdefault("provider_family", "gemini")
    cache_key_payload.setdefault("cache_retention", cache_retention)

    if cache_enabled and not cache_key_payload.get("stream"):
        try:
            cached = cache.get(cache_key_payload) if cache is not None else None
            if cached is None:
                cached = get_default_cache().get(cache_key_payload)
            if cached is not None:
                logger.debug(f"Gemini cache hit (key={make_cache_key(cache_key_payload)[:12]}…)")
                return _rehydrate_response(cached)
        except Exception:
            pass

    cfg = get_config()
    active_id = cfg.get("llm.active", "")
    api_key = cfg.get_llm_config(active_id).get("api_key", "")
    client = make_gemini_client(active_id)
    if client is None:
        return _rehydrate_response({"id": "no-gemini", "model": model, "choices": [{"index": 0, "message": {"role": "assistant", "content": "(google-genai SDK unavailable)"}, "finish_reason": "stop"}]})

    system_prompt = _extract_system_prompt(messages) or ""
    cached_content: Optional[str] = None
    if system_prompt and cache_enabled:
        try:
            cached_content = get_default_gemini_cache().ensure_cached_content(
                model_id=model,
                system_prompt=system_prompt,
                base_url=base_url,
                cache_retention=cache_retention,
                api_key=api_key,
                provider="google",
                model_api="google-genai",
            )
        except Exception:
            cached_content = None

    contents = _messages_to_gemini_contents(messages)

    try:
        from google.genai import types  # type: ignore

        gen_config: dict[str, Any] = {}
        if system_prompt:
            gen_config["system_instruction"] = system_prompt
        if cached_content:
            gen_config["cached_content"] = cached_content
        if max_tokens is not None:
            gen_config["max_output_tokens"] = int(max_tokens)
        if temperature is not None:
            gen_config["temperature"] = float(temperature)
        if tools:
            try:
                gen_config["tools"] = _convert_tools_to_gemini(tools)
            except Exception:
                pass
        cfg_obj = types.GenerateContentConfig(**gen_config) if gen_config else None
        response = client.models.generate_content(
            model=model if model.startswith("models/") else f"models/{model}",
            contents=contents,
            config=cfg_obj,
        )
    except Exception as e:
        logger.warning(f"Gemini generate_content failed: {e}")
        return _rehydrate_response({"id": "gemini-error", "model": model, "choices": [{"index": 0, "message": {"role": "assistant", "content": f"(Gemini call failed: {e})"}, "finish_reason": "stop"}]})

    out = _gemini_response_to_openai_shape(response, model)
    if cache_enabled:
        try:
            get_default_cache().put(cache_key_payload, out, cache_enabled=True)
        except Exception:
            pass
    return _rehydrate_response(out)


def _messages_to_gemini_contents(messages: list[dict]) -> list:
    """Convert OpenAI chat messages into google.genai Contents list.

    System messages are skipped — they're injected via GenerateContentConfig.
    Tool messages are merged into the prior assistant turn's tool_calls results.
    """
    from google.genai import types  # type: ignore

    out: list[Any] = []
    for m in messages:
        role = m.get("role")
        content = m.get("content", "")
        if role == "system":
            continue
        if role == "user":
            text = content if isinstance(content, str) else _extract_text_from_parts(content)
            out.append(types.Content(role="user", parts=[types.Part(text=text)]))
        elif role == "assistant":
            text = content if isinstance(content, str) else _extract_text_from_parts(content)
            out.append(types.Content(role="model", parts=[types.Part(text=text or "")]))
        elif role == "tool":
            out.append(types.Content(
                role="user",
                parts=[types.Part(text=f"[tool {m.get('tool_call_id','')}] {content if isinstance(content, str) else str(content)}")],
            ))
    return out if out else [types.Content(role="user", parts=[types.Part(text="")])]


def _extract_text_from_parts(parts: Any) -> str:
    if not parts:
        return ""
    out = []
    for p in parts:
        if isinstance(p, dict):
            if p.get("type") == "text" and p.get("text"):
                out.append(p["text"])
            elif p.get("type") == "image_url":
                out.append("[image]")
        elif hasattr(p, "text"):
            out.append(p.text)
    return "\n".join(out)


def _convert_tools_to_gemini(tools: list[dict]) -> list:
    """Best-effort OpenAI-tools → gemini-tools conversion."""
    from google.genai import types  # type: ignore

    decls = []
    for t in tools or []:
        if not isinstance(t, dict):
            continue
        fn = t.get("function") or {}
        name = fn.get("name") or t.get("name")
        if not name:
            continue
        params = fn.get("parameters") or {}
        decls.append({
            "name": name,
            "description": fn.get("description", ""),
            "parameters": params,
        })
    return [types.Tool(function_declarations=decls)] if decls else []


def _gemini_response_to_openai_shape(response: Any, model: str) -> dict:
    text = ""
    try:
        text = response.text or ""
    except Exception:
        text = ""
    return {
        "id": getattr(response, "id", "") or "gemini",
        "model": getattr(response, "model", "") or model,
        "choices": [{
            "index": 0,
            "finish_reason": "stop",
            "message": {"role": "assistant", "content": text, "tool_calls": None},
        }],
        "usage": {},
    }


# --- Anthropic-native path ---------------------------------------------------

_ANTHROPIC_LOCK = __import__("threading").Lock()


def make_anthropic_client(provider_id: str):
    """Singleton `anthropic.Anthropic` client for the named provider."""
    if provider_id in _ANTHROPIC_CLIENTS:
        return _ANTHROPIC_CLIENTS[provider_id]
    with _ANTHROPIC_LOCK:
        if provider_id in _ANTHROPIC_CLIENTS:
            return _ANTHROPIC_CLIENTS[provider_id]
        cfg = get_config().get_llm_config(provider_id)
        client = None
        try:
            import anthropic  # type: ignore

            kwargs: dict[str, Any] = {"api_key": cfg.get("api_key", "")}
            base_url = cfg.get("base_url", "")
            if base_url:
                kwargs["base_url"] = base_url
            client = anthropic.Anthropic(**kwargs)
        except Exception:
            client = None
        _ANTHROPIC_CLIENTS[provider_id] = client
        return client


def chat_completion_anthropic(
    *,
    messages: list[dict],
    model: str,
    cache: Optional[LLMCache] = None,
    cache_enabled: bool = True,
    cache_retention: str = "short",
    base_url: str = "",
    payload: Optional[dict] = None,
    tools: Any = None,
    max_tokens: int = 4096,
    temperature: Any = None,
) -> Any:
    """Drop-in for OpenAI chat.completions when provider=anthropic.

    Uses `anthropic.Anthropic.messages.create(...)` and converts the response
    back to the OpenAI shape so downstream call sites and the L1/L2 caches
    see a uniform interface.

    Cache strategy: Anthropic manages server-side cache invalidation itself
    based on `cache_control: ephemeral` markers. fsar only needs to:
      1. attach the right markers (system block + trailing user text block),
      2. record a timestamp per call so a downstream observability pass can
         detect cache-hit rate drops (mirrors openclaw's `cache-ttl.ts`).
    """
    from src.utils.anthropic_cache import (
        AnthropicCacheLog,
        anthropic_response_to_openai_shape,
        convert_messages_to_anthropic,
        convert_tools_to_anthropic,
        get_default_anthropic_cache_log,
        resolve_cache_control,
    )

    payload = payload if payload is not None else {
        "model": model, "messages": messages, "tools": tools,
        "max_tokens": max_tokens, "temperature": temperature,
    }

    cfg = get_config()
    cache_key_payload = dict(payload)
    cache_key_payload.setdefault("provider", "anthropic")
    cache_key_payload.setdefault("provider_family", "anthropic")
    cache_key_payload.setdefault("cache_retention", cache_retention)

    if cache_enabled and not cache_key_payload.get("stream"):
        try:
            cached = get_default_cache().get(cache_key_payload)
            if cached is not None:
                logger.debug(
                    f"Anthropic cache hit (key={make_cache_key(cache_key_payload)[:12]}…)"
                )
                return _rehydrate_response(cached)
        except Exception:
            pass

    provider_override = cfg.get("llm.cache.provider_override", "") or None
    cache_control = resolve_cache_control(
        cache_retention=cache_retention,
        base_url=base_url,
        provider_override=provider_override,
    )

    system_blocks, anthropic_msgs = convert_messages_to_anthropic(
        messages, cache_control
    )
    anthropic_tools = convert_tools_to_anthropic(tools)

    active_id = cfg.get("llm.active", "")
    client = make_anthropic_client(active_id)
    if client is None:
        return _rehydrate_response({
            "id": "no-anthropic",
            "model": model,
            "choices": [{
                "index": 0,
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": "(anthropic SDK unavailable)",
                    "tool_calls": None,
                },
            }],
            "usage": {},
        })

    system_text = None
    if system_blocks:
        system_text = "\n\n".join(
            b.get("text", "") for b in system_blocks if isinstance(b, dict)
        )

    if cache_enabled and system_text:
        try:
            get_default_anthropic_cache_log().append(
                provider="anthropic",
                model_id=model,
                cache_retention=cache_retention,
                system_prompt=system_text,
            )
        except Exception:
            pass

    call_kwargs: dict[str, Any] = {
        "model": model,
        "messages": anthropic_msgs,
        "max_tokens": max_tokens,
    }
    if system_blocks is not None:
        call_kwargs["system"] = system_blocks
    if anthropic_tools is not None:
        call_kwargs["tools"] = anthropic_tools
    if temperature is not None:
        call_kwargs["temperature"] = float(temperature)

    try:
        response = client.messages.create(**call_kwargs)
    except Exception as e:
        logger.warning(f"Anthropic messages.create failed: {e}")
        return _rehydrate_response({
            "id": "anthropic-error",
            "model": model,
            "choices": [{
                "index": 0,
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": f"(Anthropic call failed: {e})",
                    "tool_calls": None,
                },
            }],
            "usage": {},
        })

    out = anthropic_response_to_openai_shape(response, model)
    if cache_enabled:
        try:
            get_default_cache().put(cache_key_payload, out, cache_enabled=True)
        except Exception:
            pass
    return _rehydrate_response(out)


# --- Responses-API path (OpenAI-compatible) ----------------------------------

_RESPONSES_LOCK = __import__("threading").Lock()


def _client_supports_responses(client: Any) -> bool:
    """Check whether the OpenAI-compatible client exposes a `responses` surface.

    The official openai-python SDK ≥ 1.50 attaches `client.responses` as a
    `Responses` resource object exposing `.create()`. Custom subclasses or
    older versions may not — in which case the dispatch falls back to
    `chat.completions`.
    """
    responses = getattr(client, "responses", None)
    if responses is None:
        return False
    return callable(getattr(responses, "create", None))


def chat_completion_responses(
    client: Any,
    *,
    cache: Optional[LLMCache] = None,
    cache_enabled: Optional[bool] = None,
    cache_retention: Optional[str] = None,
    session_id: Optional[str] = None,
    base_url: str = "",
    **kwargs: Any,
) -> Any:
    """Drop-in for OpenAI Chat when the provider exposes the Responses API.

    Routes through `client.responses.create(**kwargs)` (POST /v1/responses)
    with the standard payload translation. Injects `prompt_cache_key` (the
    fsar session id) so the server's prefix cache can be reused, and
    `prompt_cache_retention="24h"` when retention=long AND the endpoint is
    api.openai.com (matching openclaw's gating).

    Streaming (`stream=True`) is supported only on the Responses surface —
    the response object differs from chat.completions and is NOT cached.

    The L1/L2 cache still keys off the **content hash** of the input
    payload; `prompt_cache_key` is server-side only.
    """
    from src.utils.responses_compat import (
        build_responses_kwargs,
        extract_system_prompt,
        responses_to_chat_shape,
    )
    from src.utils.session_id import get_or_create_session_id

    cfg = get_config()
    cache = cache if cache is not None else get_default_cache()
    if cache_enabled is None:
        cache_enabled = cfg.llm_cache_enabled and not bool(kwargs.get("stream"))
    retention = cache_retention or cfg.llm_cache_retention

    if not base_url:
        try:
            base_url = str(getattr(client, "base_url", "") or "")
        except Exception:
            base_url = ""

    payload: dict = dict(kwargs)
    if not payload.get("model"):
        raise ValueError("model must be supplied to chat_completion_responses")

    msgs = payload.get("messages") or []
    system_prompt = extract_system_prompt(msgs) if msgs else ""

    session = session_id or get_or_create_session_id(
        cache_db_path=cfg.llm_cache_db_path,
        override=cfg.llm_cache_session_id or None,
    )

    cache_key_payload = dict(payload)
    cache_key_payload.setdefault("provider", "openai")
    cache_key_payload.setdefault("provider_family", "openai")
    cache_key_payload.setdefault("api", "responses")
    cache_key_payload.setdefault("cache_retention", retention)
    cache_key_payload["system_prompt"] = system_prompt

    if cache_enabled:
        try:
            cached = cache.get(cache_key_payload)
            if cached is not None:
                logger.debug(
                    f"Responses cache hit (key={make_cache_key(cache_key_payload)[:12]}…)"
                )
                return _rehydrate_response(cached)
        except Exception:
            pass

    if not _client_supports_responses(client):
        logger.warning(
            "use_responses_api=True but client lacks `responses` surface; "
            "falling back to chat.completions"
        )
        fallback_kwargs = {k: v for k, v in kwargs.items() if k != "session_id"}
        fallback_kwargs["_skip_responses_dispatch"] = True
        return cached_chat_completion(
            client,
            cache=cache,
            cache_enabled=cache_enabled,
            cache_retention=retention,
            **fallback_kwargs,
        )

    responses_kwargs = build_responses_kwargs(
        payload=payload,
        system_prompt=system_prompt,
        session_id=session,
        cache_retention=retention,
        base_url=base_url,
    )

    try:
        response = client.responses.create(**responses_kwargs)
    except Exception as e:
        logger.warning(f"responses.create failed: {e}")
        try:
            return _rehydrate_response({
                "id": "responses-error",
                "model": payload.get("model", ""),
                "choices": [{
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": f"(Responses API call failed: {e})",
                        "tool_calls": None,
                    },
                }],
                "usage": {},
            })
        except Exception:
            return None

    if bool(kwargs.get("stream")):
        return response

    try:
        out = responses_to_chat_shape(response, str(payload.get("model", "")))
    except Exception as e:
        logger.warning(f"Responses response normalization failed: {e}")
        out = {
            "id": "responses-parse-error",
            "model": str(payload.get("model", "")),
            "choices": [{
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": str(response)[:4000], "tool_calls": None},
            }],
            "usage": {},
        }

    if cache_enabled:
        try:
            cache.put(cache_key_payload, out, cache_enabled=True)
        except Exception:
            pass

    return _rehydrate_response(out)


def _rehydrate_response(stored: Any) -> Any:
    """Wrap a cached response dict into a namespace that the rest of the codebase
    can read like the SDK's response object.

    Most call sites only touch `response.choices[0].message.content` and
    `response.choices[0].message.tool_calls`, so a thin namespace wrapper is
    enough.
    """

    class _Msg:
        def __init__(self, m: dict):
            self.content = m.get("content", "") or ""
            self.role = m.get("role", "assistant")
            self.tool_calls = m.get("tool_calls")
            self.reasoning = m.get("reasoning", "")

    class _Choice:
        def __init__(self, c: dict):
            self.index = c.get("index", 0)
            msg = c.get("message", {})
            self.message = _Msg(msg)
            self.finish_reason = c.get("finish_reason", "stop")

    class _Resp:
        def __init__(self, data: dict):
            self.id = data.get("id", "cached")
            self.model = data.get("model", "")
            self.choices = [_Choice(c) for c in data.get("choices", [])]
            self.usage = data.get("usage") or {}

    if isinstance(stored, dict):
        return _Resp(stored)
    return stored


def reset_clients() -> None:
    """Forget cached client instances across all provider families so a
    provider switch rebuilds fresh clients on the next call."""
    with _FACTORY_LOCK:
        _CLIENTS.clear()
    try:
        with _GEMINI_LOCK:
            _GEMINI_CLIENTS.clear()
    except NameError:
        pass
    try:
        with _ANTHROPIC_LOCK:
            _ANTHROPIC_CLIENTS.clear()
    except NameError:
        pass

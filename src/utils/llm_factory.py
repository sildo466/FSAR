"""Shared LLM client factory — provider family dispatch.

Wraps the OpenAI Python SDK so every `chat.completions.create` call site goes
through a single dispatcher that routes by provider family:

- openai: OpenAI-compatible `client.chat.completions.create`, or the Responses
  API when the provider's `format` is "responses".
- gemini: routes through `google.genai.Client.models.generate_content`.
- anthropic: routes through `anthropic.Anthropic.messages.create` and converts
  the response back to the OpenAI shape.

Provider **server-side prompt cache** markers are still applied where the
provider supports them: Anthropic `cache_control`, Gemini `cachedContents`
(via src.utils.gemini_cache), and Responses API `prompt_cache_key`. The
disk-level L1/L2 response cache has been removed.

Public surface:
- make_llm_client(provider_id: str) -> OpenAI-compatible client
- chat_completion(client, **kwargs) -> OpenAI-compatible response
  (drop-in replacement for `client.chat.completions.create(**kwargs)`)
- detect_provider_family(model, base_url) -> "anthropic" | "gemini" | "openai"
- apply_provider_cache_markers(messages, **kwargs) -> updated messages + kwargs
"""

from __future__ import annotations

import copy
import hashlib
import json
import ssl
from typing import Any, Optional

import httpx
from openai import OpenAI

from src.utils.config import get_config
from src.utils.logger import logger


_CLIENTS: dict[str, OpenAI] = {}
_GEMINI_CLIENTS: dict[str, Any] = {}
_ANTHROPIC_CLIENTS: dict[str, Any] = {}
_FACTORY_LOCK = __import__("threading").Lock()


def _record_global_token_usage(provider: str, model: str, response: Any) -> None:
    try:
        usage = response.get("usage") if isinstance(response, dict) else getattr(response, "usage", None)
        if usage is None:
            return
        get = usage.get if isinstance(usage, dict) else lambda key, default=0: getattr(usage, key, default)
        input_tokens = int(get("input_tokens", get("prompt_tokens", 0)) or 0)
        output_tokens = int(get("output_tokens", get("completion_tokens", 0)) or 0)
        from src.memory.integrations import record_token_usage
        from src.providers.pricing import cost_usd

        run_id = None
        try:
            from src.server.integration_engine import current_integration_run_id

            run_id = current_integration_run_id()
        except Exception:
            pass
        record_token_usage(
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            integration_run_id=run_id,
            cost_usd=cost_usd(provider, model, input_tokens, output_tokens),
        )
    except Exception as exc:
        logger.debug(f"token usage record skipped: {exc}")


def detect_provider_family(model: str = "", base_url: str = "") -> str:
    """Best-effort provider family detection.

    Inspects (in order): explicit `provider` override, model id prefix, base
    URL host substring. Defaults to "openai".
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


def _stable_dumps(obj: Any) -> str:
    """Deterministic JSON: sort_keys, ensure_ascii off, separators tight."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


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
    """Mutate (in a copy) messages + kwargs to inject provider-specific
    **server-side** prompt-cache markers. Returns (messages, kwargs, extra_body).

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
    elif family == "gemini":
        # Gemini-side prompt cache reference. Returned in `body` so the
        # caller (chat_completion → chat_completion_gemini) can pull it out
        # and inject into GenerateContentConfig.cached_content. The actual
        # POST/PATCH against the cachedContents API lives in
        # src/utils/gemini_cache.py.
        body.setdefault("cached_content", "")
    else:
        # OpenAI-compatible relays that accept prompt_cache_key for sticky
        # routing — only set it when caller opted in (cache_retention == "long").
        if cache_retention == "long":
            body.setdefault("prompt_cache_key", _derive_cache_key(model, msgs))

    return msgs, {}, body


def _derive_cache_key(model: str, messages: list[dict]) -> str:
    return hashlib.sha256(_stable_dumps({"model": model, "messages": messages}).encode("utf-8")).hexdigest()[:32]


def make_llm_client(provider_id: str, base_url: str = "", api_key: str = "") -> OpenAI:
    """Return a singleton OpenAI client for the named provider.

    All call sites that need an LLM should use this instead of constructing
    `OpenAI(...)` themselves, so client wiring (SSL workaround, base_url,
    api_key) is uniform.
    """
    key_suffix = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:8] if api_key else ""
    client_key = "\n".join((provider_id, base_url, key_suffix))
    if client_key in _CLIENTS:
        return _CLIENTS[client_key]
    with _FACTORY_LOCK:
        if client_key in _CLIENTS:
            return _CLIENTS[client_key]
        cfg = get_config().get_llm_config(provider_id)
        resolved_base_url = base_url or cfg.get("base_url", "")
        resolved_api_key = api_key or cfg.get("api_key", "")
        ctx = ssl.create_default_context()
        try:
            client = OpenAI(
                api_key=resolved_api_key,
                base_url=resolved_base_url,
                http_client=httpx.Client(verify=ctx),
            )
        except TypeError:
            # OpenAI SDK < 1.0 or custom subclasses: fall back without http_client.
            client = OpenAI(
                api_key=resolved_api_key,
                base_url=resolved_base_url,
            )
        _CLIENTS[client_key] = client
        return client


def chat_completion(
    client: OpenAI,
    *,
    provider_id: Optional[str] = None,
    format_override: Optional[str] = None,
    cache_retention: str = "",
    usage_recording: bool = True,
    **kwargs: Any,
) -> Any:
    """Drop-in replacement for `client.chat.completions.create(**kwargs)`.

    Dispatches by provider family:
    - gemini → `chat_completion_gemini` (official `google.genai` SDK).
    - anthropic → `chat_completion_anthropic`.
    - responses format → `chat_completion_responses` (Responses API).
    - otherwise → plain `client.chat.completions.create`.

    Server-side prompt-cache markers are injected per family (Anthropic
    cache_control / Gemini cachedContents / Responses prompt_cache_key);
    `cache_retention` ("none" | "short" | "long") controls their strength.

    Streaming (`stream=True`) is passed straight through to the real call.

    `provider_id` is optional; when supplied, its `format` field decides
    whether to route through the Responses API (`format="responses"`).
    `format_override` ("chat" | "responses" | "anthropic") takes precedence
    over the provider-level format for this single call.
    """
    cfg = get_config()
    base_url = ""
    try:
        base_url = str(getattr(client, "base_url", "") or "")
    except Exception:
        base_url = ""

    retention = cache_retention or cfg.llm_cache_retention

    provider_format = str(format_override or "")
    if provider_id and not provider_format:
        provider_format = str(cfg.get_llm_config(provider_id).get("format", "") or "")
    if not provider_format:
        active = cfg.get_active_provider()
        provider_format = str(active.get("format", "") or "")
    logger.debug(
        f"llm dispatch: model={kwargs.get('model')!r} "
        f"format_override={format_override or '-'} resolved_format={provider_format or '-'}"
    )

    payload: dict = dict(kwargs)
    if not payload.get("model"):
        raise ValueError("model must be supplied to chat_completion")

    def _with_usage(response: Any) -> Any:
        if usage_recording and not payload.get("stream"):
            _record_global_token_usage(provider_id or "", str(payload.get("model", "")), response)
        return response

    msgs = payload.get("messages") or []
    family = detect_provider_family(str(payload.get("model", "")), base_url)

    # Server-side prompt-cache marker injection (Anthropic cache_control /
    # Gemini cached_content stub / Responses prompt_cache_key).
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

    if family == "gemini" and provider_format not in ("chat", "responses", "anthropic") and not payload.get("stream"):
        return _with_usage(chat_completion_gemini(
            messages=payload["messages"],
            model=str(payload.get("model", "")),
            cache_retention=retention,
            base_url=base_url,
            extra_body=body_out,
            tools=payload.get("tools"),
            tool_choice=payload.get("tool_choice"),
            max_tokens=payload.get("max_tokens"),
            temperature=payload.get("temperature"),
        ))

    if (
        provider_format == "anthropic"
        or (family == "anthropic" and provider_format not in ("chat", "responses"))
    ) and not payload.get("stream"):
        return _with_usage(chat_completion_anthropic(
            messages=payload["messages"],
            model=str(payload.get("model", "")),
            cache_retention=retention,
            base_url=base_url,
            tools=payload.get("tools"),
            max_tokens=payload.get("max_tokens") or 4096,
            temperature=payload.get("temperature"),
        ))

    if (
        provider_format == "responses"
        and not payload.get("stream")
        and not kwargs.get("_skip_responses_dispatch", False)
    ):
        return _with_usage(chat_completion_responses(
            client,
            cache_retention=retention,
            base_url=base_url,
            **{k: v for k, v in kwargs.items() if k != "_skip_responses_dispatch"},
        ))

    chat = client.chat.completions
    create = chat.create
    response = create(**payload)
    return _with_usage(response)


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
    cache_retention: str = "short",
    base_url: str = "",
    extra_body: Optional[dict] = None,
    tools: Any = None,
    tool_choice: Any = None,
    max_tokens: Any = None,
    temperature: Any = None,
) -> Any:
    """Drop-in for OpenAI chat.completions when provider=gemini.

    Routes through `google.genai.Client.models.generate_content`. The
    stable prefix is extracted as the leading system prompt(s) and a
    cachedContent reference is requested via GeminiPromptCache (server-side
    prompt cache).
    """
    from src.utils.gemini_cache import get_default_gemini_cache

    cfg = get_config()
    active_id = cfg.get("llm.active", "")
    api_key = cfg.get_llm_config(active_id).get("api_key", "")
    client = make_gemini_client(active_id)
    if client is None:
        return _rehydrate_response({"id": "no-gemini", "model": model, "choices": [{"index": 0, "message": {"role": "assistant", "content": "(google-genai SDK unavailable)"}, "finish_reason": "stop"}]})

    system_prompt = _extract_system_prompt(messages) or ""
    cached_content: Optional[str] = None
    if system_prompt and cache_retention != "none":
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
    cache_retention: str = "short",
    base_url: str = "",
    tools: Any = None,
    max_tokens: int = 4096,
    temperature: Any = None,
) -> Any:
    """Drop-in for OpenAI chat.completions when provider=anthropic.

    Uses `anthropic.Anthropic.messages.create(...)` and converts the response
    back to the OpenAI shape so downstream call sites see a uniform interface.

    Server-side prompt cache: attaches `cache_control: ephemeral` markers to
    the system block + trailing user text block, and records a timestamp for
    cache-break observability (Anthropic manages invalidation server-side).
    """
    from src.utils.anthropic_cache import (
        AnthropicCacheLog,
        anthropic_response_to_openai_shape,
        convert_messages_to_anthropic,
        convert_tools_to_anthropic,
        get_default_anthropic_cache_log,
        resolve_cache_control,
    )

    cfg = get_config()
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

    if cache_retention != "none" and system_blocks:
        try:
            system_text = "\n\n".join(
                b.get("text", "") for b in system_blocks if isinstance(b, dict)
            )
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
    session_id: Optional[str] = None,
    cache_retention: str = "",
    base_url: str = "",
    **kwargs: Any,
) -> Any:
    """Drop-in for OpenAI Chat when the provider exposes the Responses API.

    Routes through `client.responses.create(**kwargs)` (POST /v1/responses)
    with the standard payload translation. Injects `prompt_cache_key` (the
    fsar session id) so the server's prefix cache can be reused.

    Streaming (`stream=True`) is supported on the Responses surface — the
    response object differs from chat.completions.
    """
    from src.utils.responses_compat import (
        build_responses_kwargs,
        extract_system_prompt,
        responses_to_chat_shape,
    )
    from src.utils.session_id import get_or_create_session_id

    cfg = get_config()
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

    if not _client_supports_responses(client):
        logger.warning(
            "provider format=responses but client lacks `responses` surface; "
            "falling back to chat.completions"
        )
        fallback_kwargs = {k: v for k, v in kwargs.items() if k != "session_id"}
        fallback_kwargs["_skip_responses_dispatch"] = True
        return chat_completion(client, **fallback_kwargs)

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
        status = getattr(e, "status_code", None)
        request_url = ""
        err_response = getattr(e, "response", None)
        if err_response is not None:
            request_url = str(getattr(err_response, "url", "") or "")
        detail = str(e)
        if status is not None or request_url:
            detail = f"{e} (status={status}, url={request_url})"
        logger.warning(f"responses.create failed: {detail}")
        try:
            return _rehydrate_response({
                "id": "responses-error",
                "model": payload.get("model", ""),
                "choices": [{
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": f"(Responses API call failed: {detail})",
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

    return _rehydrate_response(out)


def _rehydrate_response(stored: Any) -> Any:
    """Wrap a response dict into a namespace that the rest of the codebase can
    read like the SDK's response object.

    Most call sites only touch `response.choices[0].message.content` and
    `response.choices[0].message.tool_calls`, so a thin namespace wrapper is
    enough.
    """

    class _ToolCallFunction:
        def __init__(self, fn: dict):
            self.name = fn.get("name", "")
            self.arguments = fn.get("arguments", "")

    class _ToolCall:
        def __init__(self, t: dict):
            self.id = t.get("id", "")
            self.type = t.get("type", "function")
            self.function = _ToolCallFunction(t.get("function") or {})

    class _Msg:
        def __init__(self, m: dict):
            self.content = m.get("content", "") or ""
            self.role = m.get("role", "assistant")
            raw_tcs = m.get("tool_calls")
            if isinstance(raw_tcs, list):
                self.tool_calls = [_ToolCall(tc) for tc in raw_tcs if isinstance(tc, dict)]
            else:
                self.tool_calls = raw_tcs
            self.reasoning = m.get("reasoning", "")

        def get(self, key, default=None):
            """Dict-style read for callers that treat messages as mappings."""
            return getattr(self, key, default)

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

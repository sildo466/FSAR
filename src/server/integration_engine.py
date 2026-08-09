"""Recursive three-phase integration execution."""

from __future__ import annotations

import contextvars
import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from src.core.prompts import build_system_prompt
from src.memory.integrations import (
    CycleError,
    Integration,
    IntegrationSub,
    ModelSpec,
    get_integration,
    get_model,
    record_token_usage,
)
from src.providers.pricing import cost_usd
from src.utils.fsar_config import get_default_config
from src.utils.llm_factory import cached_chat_completion, make_llm_client
from src.utils.logger import logger

_run_id_var: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "integration_run_id", default=None
)
_trace_var: contextvars.ContextVar["ExecutionTrace | None"] = contextvars.ContextVar(
    "integration_trace", default=None
)
_system_prompt_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "integration_system_prompt", default=None
)


def current_integration_run_id() -> int | None:
    return _run_id_var.get()


@dataclass
class ExecutionTrace:
    route: dict[str, Any] | None = None
    debate: list[dict[str, Any]] = field(default_factory=list)
    calls: int = 0
    total_cost_usd: float | None = 0.0
    errors: list[str] = field(default_factory=list)


def _normalise_usage(usage: Any) -> dict[str, int]:
    if usage is None:
        return {"input_tokens": 0, "output_tokens": 0}
    get = usage.get if isinstance(usage, dict) else lambda key, default=0: getattr(usage, key, default)
    return {
        "input_tokens": int(get("input_tokens", get("prompt_tokens", 0)) or 0),
        "output_tokens": int(get("output_tokens", get("completion_tokens", 0)) or 0),
    }


def _provider_id(provider: str) -> str:
    config = get_default_config()
    if config.get_llm_config(provider):
        return provider
    for row in config.list_providers(enabled_only=True):
        if row.get("family") == provider or row.get("id") == provider:
            return str(row.get("id", provider))
    return provider


def _call_provider(provider: str, model: str, messages: list[dict[str, Any]], *,
                   temperature: float = 0.7, json_mode: bool = False,
                   max_tokens: int | None = None, base_url: str = "",
                   api_key: str = "", protocol: str = "",
                   **kwargs: Any) -> tuple[str, dict[str, int]]:
    """Call one configured provider and record normalized usage."""
    provider_id = _provider_id(provider)
    logger.info(
        f"integration call: model={model!r} provider={provider_id!r} "
        f"protocol={protocol or 'auto'} base_url={base_url or '(provider default)'}"
    )
    client = make_llm_client(provider_id, base_url=base_url, api_key=api_key)
    if client is None:
        raise RuntimeError(f"provider unavailable: {provider}")
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
        "cache_enabled": False,
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    payload.update(kwargs)
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    call_kwargs: dict[str, Any] = {"provider_id": provider_id, "usage_recording": False}
    if protocol in ("chat", "responses", "anthropic"):
        call_kwargs["format_override"] = protocol
    response = cached_chat_completion(client, **call_kwargs, **payload)
    message = response.choices[0].message if getattr(response, "choices", None) else None
    text = str(getattr(message, "content", "") or "") if message is not None else str(response or "")
    usage = _normalise_usage(getattr(response, "usage", None))
    return text, usage


def _invoke_provider(*args: Any, **kwargs: Any) -> tuple[str, dict[str, int]]:
    result = _call_provider(*args, **kwargs)
    trace = _trace_var.get()
    if trace is not None:
        trace.calls += 1
        provider, model = str(args[0]), str(args[1])
        usage = result[1]
        price = cost_usd(provider, model, usage["input_tokens"], usage["output_tokens"])
        if price is None:
            trace.total_cost_usd = None
        elif trace.total_cost_usd is not None:
            trace.total_cost_usd += price
        try:
            record_token_usage(
                provider=provider,
                model=model,
                input_tokens=usage["input_tokens"],
                output_tokens=usage["output_tokens"],
                integration_run_id=_run_id_var.get(),
                cost_usd=price,
            )
        except Exception:
            pass
    return result


def _resolve_node(node: Any) -> tuple[str, ModelSpec | Integration]:
    if isinstance(node, ModelSpec):
        return "model", node
    if isinstance(node, Integration):
        return "integration", node
    if isinstance(node, dict):
        kind = node.get("kind")
        if kind == "model":
            if node.get("id") is not None and not node.get("provider"):
                return "model", get_model(int(node["id"]))
            return "model", ModelSpec(
                id=node.get("id"), provider=str(node.get("provider", "")),
                model=str(node.get("model", "")), persona_prompt=str(node.get("persona_prompt", "")),
                base_url=str(node.get("base_url", "")),
                api_key=str(node.get("api_key", "")),
                protocol=str(node.get("protocol", "")),
                specialty=str(node.get("specialty", "")), temperature=float(node.get("temperature", 0.7)),
                max_tokens=node.get("max_tokens"),
            )
        if kind == "integration":
            return "integration", get_integration(int(node["id"]))
    if isinstance(node, int):
        return "integration", get_integration(node)
    raise ValueError(f"unknown integration node: {node!r}")


def _full_chat_system() -> str:
    provided = _system_prompt_var.get()
    if provided:
        return provided
    try:
        return build_system_prompt(mode="agent", character=None, user_card=None)
    except Exception:
        return "You are the main integration agent. Reply directly and accurately."


def _build_main_messages(node: Integration, user_msg: str,
                         session_messages: list[dict[str, Any]] | None,
                         *, phase: str, extras: list[str] | None = None) -> list[dict[str, Any]]:
    blocks: list[str] = []
    if phase == "route":
        available: list[str] = []
        for sub in node.subs:
            if sub.kind == "model":
                try:
                    model = get_model(int(sub.model_id))
                    specialty = model.specialty
                except Exception:
                    specialty = ""
                available.append(f'- "{sub.display_name}" {specialty}'.rstrip())
            else:
                try:
                    child = get_integration(int(sub.child_integration_id))
                    main = get_model(child.main_model_id)
                    available.append(f'- "{sub.display_name}" (integration; {main.specialty})'.rstrip())
                except Exception:
                    available.append(f'- "{sub.display_name}" (integration)')
        blocks.append("[AVAILABLE SUB-AGENTS]\n" + "\n".join(available))
        blocks.append(
            '[INSTRUCTION]\nDecide which sub-agents are relevant for this message.\n'
            'Output JSON: {"selected": ["<name>", ...], "reasoning": "..."}\n'
            'Output {"selected": []} if no subs are useful.'
        )
    elif phase == "synth":
        blocks.append("[INSTRUCTION]\nSynthesize a single final reply for the user.")
    if extras:
        blocks.extend(extras)
    system = _full_chat_system()
    if blocks:
        system += "\n\n" + "\n\n".join(blocks)
    return [{"role": "system", "content": system}, *(session_messages or []), {"role": "user", "content": user_msg}]


def _build_main_messages_for_leaf(model: ModelSpec, user_msg: str,
                                  session_messages: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    return [{"role": "system", "content": model.persona_prompt}, *(session_messages or []), {"role": "user", "content": user_msg}]


def build_chat_assembly(*, mode: str = "chat") -> str:
    try:
        return build_system_prompt(mode="agent" if mode == "agent" else "companion", character=None, user_card=None)
    except Exception:
        return "You are the main integration agent."


def build_chat_assembly_for_sub(model: ModelSpec) -> str:
    return model.persona_prompt


def _build_sub_messages(model: ModelSpec, user_msg: str, round_no: int,
                        total_rounds: int, peers: dict[str, str], name: str = "") -> list[dict[str, Any]]:
    system = model.persona_prompt or "You are a specialist sub-agent."
    system += (
        f"\n\n## Sub-agent: {name}\n## Debate Protocol\n"
        f"- Round {round_no} of {total_rounds}\n"
        "- You see peer sub-agents' latest positions.\n"
        "- Output [CONSENSUS] at the end of your reply if the answer is settled."
    )
    content = user_msg
    if peers:
        lines = ["---", "", f"## Current peer positions (round {round_no - 1}):"]
        for name, text in peers.items():
            lines.extend([f'### "{name}"', text])
        content += "\n" + "\n".join(lines)
    return [{"role": "system", "content": system}, {"role": "user", "content": content}]


def _sub_call_messages(model: ModelSpec, user_msg: str, round_no: int,
                       total_rounds: int, peers: list[dict[str, Any]] | None = None) -> tuple[str, str]:
    peer_map = {str(item.get("name", "")): str(item.get("text", "")) for item in (peers or [])}
    messages = _build_sub_messages(model, user_msg, round_no, total_rounds, peer_map)
    return str(messages[0]["content"]), str(messages[1]["content"])


def _parse_route_json(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    candidates = [raw]
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.I | re.S)
    if fenced:
        candidates.insert(0, fenced.group(1))
    inline = re.search(r"\{\s*[\"']selected[\"']\s*:\s*\[.*?\].*?\}", raw, re.S)
    if inline:
        candidates.append(inline.group(0))
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and isinstance(data.get("selected"), list):
            selected = [str(item) for item in data["selected"] if isinstance(item, (str, int))]
            return {"selected": selected, "reasoning": str(data.get("reasoning", "") or "")}
    raise ValueError("could not parse route JSON")


def _has_consensus(reply_text: str) -> bool:
    return re.search(r"\[consensus\]\s*\.?\s*$", str(reply_text or ""), re.I) is not None


def _is_cancelled(cancel_token: Any) -> bool:
    if cancel_token is None:
        return False
    if isinstance(cancel_token, dict):
        return bool(cancel_token.get("set"))
    checker = getattr(cancel_token, "is_set", None)
    if callable(checker):
        return bool(checker())
    return bool(getattr(cancel_token, "set", False))


def _check_cancelled(cancel_token: Any) -> None:
    if _is_cancelled(cancel_token):
        import asyncio

        raise asyncio.CancelledError()


def _cycle_run_time_check(intg_id: int, ancestors: set[int]) -> None:
    if intg_id in ancestors:
        raise CycleError(intg_id, list(ancestors) + [intg_id])


def _is_sub_call_marker(messages: Any) -> bool:
    return "## Debate Protocol" in str(messages)


def _run_debate(node: Integration, chosen_subs: list[IntegrationSub], user_msg: str,
                ancestors: set[int] | None = None, depth: int = 0,
                cancel_token: Any = None) -> list[dict[str, Any]]:
    transcript: list[dict[str, Any]] = []
    latest: dict[str, str] = {}
    for round_no in range(1, max(1, int(node.rounds)) + 1):
        if _is_cancelled(cancel_token):
            for sub in chosen_subs:
                latest[sub.display_name] = "[cancelled]"
            transcript.append({"round": round_no, "replies": dict(latest)})
            break
        replies: dict[str, str] = {}
        for sub in chosen_subs:
            if _is_cancelled(cancel_token):
                text = "[cancelled]"
            else:
                try:
                    if sub.kind == "integration":
                        _cycle_run_time_check(int(sub.child_integration_id), set(ancestors or set()))
                        if depth + 1 >= node.max_depth:
                            text = f"[nest exceed: {sub.display_name}]"
                            replies[sub.display_name] = text
                            continue
                        text = execute(
                            {"kind": "integration", "id": sub.child_integration_id},
                            user_msg, ancestors=ancestors, depth=depth + 1,
                            cancel_token=cancel_token,
                        )
                    else:
                        model = get_model(int(sub.model_id))
                        text, _ = _invoke_provider(
                            model.provider, model.model,
                            _build_sub_messages(model, user_msg, round_no, node.rounds, latest, sub.display_name),
                            temperature=model.temperature,
                            max_tokens=model.max_tokens,
                            base_url=model.base_url,
                            api_key=model.api_key,
                            protocol=model.protocol,
                        )
                except CycleError:
                    raise
                except Exception as exc:
                    text = f"[sub error: {exc}]"
                    logger.warning(
                        f"integration sub call failed: {sub.display_name} "
                        f"(round {round_no}): {exc}"
                    )
                    trace = _trace_var.get()
                    if trace is not None:
                        trace.errors.append(text)
            replies[sub.display_name] = str(text)
        transcript.append({"round": round_no, "replies": replies})
        latest = replies
        if replies and all(_has_consensus(text) for text in replies.values()):
            break
    trace = _trace_var.get()
    if trace is not None:
        trace.debate = transcript
    return transcript


def _format_debate(debate: list[dict[str, Any]]) -> str:
    total = len(debate)
    sections: list[str] = []
    for entry in debate:
        sections.append(f"(round {entry.get('round', 0)} of {total})")
        for name, text in (entry.get("replies") or {}).items():
            sections.append(f'### "{name}"\n{text}')
    return "\n".join(sections) if sections else "(no debate)"


CycleRuntimeError = CycleError


def _synthesize(node: Integration, user_msg: str,
                session_messages: list[dict[str, Any]] | None,
                route: dict[str, Any], debate: list[dict[str, Any]]) -> str:
    appendix = ["---", "", "## Routing decision", route.get("reasoning", "")]
    if debate:
        appendix.extend(["", "## Debate transcript", _format_debate(debate)])
    messages = _build_main_messages(node, user_msg + "\n" + "\n".join(appendix), session_messages, phase="synth")
    main = get_model(node.main_model_id)
    try:
        text, _ = _invoke_provider(
            main.provider,
            main.model,
            messages,
            temperature=main.temperature,
            max_tokens=main.max_tokens,
            base_url=main.base_url,
            api_key=main.api_key,
            protocol=main.protocol,
        )
        return text
    except Exception as exc:
        longest = ""
        for entry in debate:
            for candidate in (entry.get("replies") or {}).values():
                if isinstance(candidate, str) and len(candidate) > len(longest):
                    longest = candidate
        if not longest:
            raise
        return f"[synthesizer error: {exc}]\n\n---\nFallback (longest sub reply):\n\n{longest}"


def _synthesize_with_fallback(node: Integration, user_msg: str,
                              session_messages: list[dict[str, Any]] | None,
                              route: dict[str, Any], debate: list[dict[str, Any]]) -> str:
    return _synthesize(node, user_msg, session_messages, route, debate)


def execute(node: Any, user_msg: str, *, session_messages: list[dict[str, Any]] | None = None,
            ancestors: set[int] | None = None, depth: int = 0, cancel_token: Any = None) -> str:
    kind, resolved = _resolve_node(node)
    if kind == "model":
        model = resolved
        if _is_cancelled(cancel_token):
            return "[cancelled]"
        messages = [
            {"role": "system", "content": model.persona_prompt},
            {"role": "user", "content": user_msg},
        ]
        text, _ = _invoke_provider(model.provider, model.model, messages,
                                 temperature=model.temperature, max_tokens=model.max_tokens,
                                 base_url=model.base_url, api_key=model.api_key,
                                 protocol=model.protocol)
        return text

    node = resolved
    assert isinstance(node, Integration)
    ancestors = set(ancestors or set())
    if node.id is not None:
        _cycle_run_time_check(node.id, ancestors)
    if depth > node.max_depth:
        return f"[nest exceed: {node.name}]"
    next_ancestors = ancestors | ({node.id} if node.id is not None else set())
    main = get_model(node.main_model_id)
    route_messages = _build_main_messages(node, user_msg, session_messages, phase="route")
    if _is_cancelled(cancel_token):
        route = {"selected": [], "reasoning": "cancelled"}
    else:
        try:
            route_text, _ = _invoke_provider(main.provider, main.model, route_messages,
                                           temperature=main.temperature, max_tokens=main.max_tokens,
                                           base_url=main.base_url, api_key=main.api_key,
                                           protocol=main.protocol, json_mode=True)
            route = _parse_route_json(route_text)
        except Exception as exc:
            route = {"selected": [sub.display_name for sub in node.subs], "reasoning": f"fallback: {exc}"}
            trace = _trace_var.get()
            if trace is not None:
                trace.errors.append(str(exc))
    trace = _trace_var.get()
    if trace is not None:
        trace.route = route
    selected = set(route.get("selected", []))
    limit = len(node.subs) if not node.max_subs_picked else min(len(node.subs), int(node.max_subs_picked))
    chosen = [sub for sub in node.subs if sub.display_name in selected][:limit]
    debate = _run_debate(node, chosen, user_msg, next_ancestors, depth, cancel_token) if chosen else []
    return _synthesize(node, user_msg, session_messages, route, debate)


def execute_detailed(node: Any, user_msg: str, *, session_messages: list[dict[str, Any]] | None = None,
                     run_id: int | None = None, cancel_token: Any = None,
                     system_prompt: str | None = None) -> tuple[str, ExecutionTrace]:
    trace = ExecutionTrace()
    token_trace = _trace_var.set(trace)
    token_run = _run_id_var.set(run_id)
    token_system = _system_prompt_var.set(system_prompt)
    try:
        return execute(node, user_msg, session_messages=session_messages, cancel_token=cancel_token), trace
    finally:
        _trace_var.reset(token_trace)
        _run_id_var.reset(token_run)
        _system_prompt_var.reset(token_system)


def execute_for_test_panel(integration_id: int, user_msg: str) -> dict[str, Any]:
    text, trace = execute_detailed({"kind": "integration", "id": integration_id}, user_msg)
    return {
        "final_reply": text,
        "route": trace.route,
        "debate": trace.debate,
        "total_calls": trace.calls,
        "total_cost_usd": trace.total_cost_usd,
    }


async def execute_async(node: Any, user_msg: str, **kwargs: Any) -> str:
    import asyncio

    return await asyncio.to_thread(execute, node, user_msg, **kwargs)


def execute_from_chat(integration_id: int, user_msg: str, *, session_messages: list[dict[str, Any]] | None = None,
                      cancel_token: Any = None, system_prompt: str | None = None) -> str:
    text, _ = execute_detailed(
        {"kind": "integration", "id": integration_id},
        user_msg,
        session_messages=session_messages,
        cancel_token=cancel_token,
        system_prompt=system_prompt,
    )
    return text


__all__ = [
    "ExecutionTrace", "execute", "execute_async", "execute_detailed", "execute_from_chat", "execute_for_test_panel",
    "build_chat_assembly", "build_chat_assembly_for_sub",
    "_call_provider", "_parse_route_json", "_has_consensus", "_run_debate", "_format_debate",
    "_sub_call_messages", "_build_main_messages", "_build_main_messages_for_leaf", "CycleRuntimeError",
    "_synthesize_with_fallback", "_check_cancelled", "_is_sub_call_marker", "_cycle_run_time_check",
    "current_integration_run_id",
]

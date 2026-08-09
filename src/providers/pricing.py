"""Static model pricing and integration call-count estimation."""

from __future__ import annotations

from typing import Optional

from src.memory.integrations import (
    Integration,
    IntegrationSub,
    ModelSpec,
    _registered_integration,
    _registered_model,
    get_integration,
    get_model,
)

MODEL_PRICING: dict[tuple[str, str], tuple[float, float]] = {
    ("openai", "gpt-4o-mini"): (0.15, 0.60),
    ("openai", "gpt-4o"): (2.50, 10.00),
    ("openai", "o1-mini"): (3.00, 12.00),
    ("openai", "o1-pro"): (15.00, 60.00),
    ("anthropic", "claude-haiku-4-5-20251001"): (0.80, 4.00),
    ("anthropic", "claude-sonnet-4-6"): (3.00, 15.00),
    ("deepseek", "deepseek-chat"): (0.14, 0.28),
    ("deepseek", "deepseek-reasoner"): (0.14, 2.19),
    ("google", "gemini-1.5-flash"): (0.075, 0.30),
    ("google", "gemini-1.5-pro"): (1.25, 5.00),
}


def cost_usd(provider: str, model: str, input_tokens: int, output_tokens: int) -> Optional[float]:
    pricing = MODEL_PRICING.get((provider, model))
    if pricing is None:
        return None
    input_rate, output_rate = pricing
    return input_tokens * input_rate / 1_000_000 + output_tokens * output_rate / 1_000_000


def _resolve_model_node(model_id: int | None) -> ModelSpec:
    if model_id is None:
        raise ValueError("model id is required")
    return _registered_model(model_id) or get_model(model_id)


def _resolve_integration_node(integration_id: int | None) -> Integration:
    if integration_id is None:
        raise ValueError("integration id is required")
    return _registered_integration(integration_id) or get_integration(integration_id)


def estimate_calls(node: ModelSpec | Integration | dict, depth: int = 0) -> int:
    """Return a deterministic upper-bound count for one execution.

    Integrations always spend one route and one synthesis call. A selected
    child is evaluated once per debate round; depth caps become a canned leaf.
    """
    if isinstance(node, ModelSpec) or (isinstance(node, dict) and node.get("kind") == "model"):
        return 1
    if isinstance(node, dict):
        if node.get("kind") != "integration":
            return 0
        try:
            node = _resolve_integration_node(int(node["id"]))
        except Exception:
            return 1
    if not isinstance(node, Integration):
        return 0
    if depth >= node.max_depth:
        return 1
    if not node.subs:
        return 2
    limit = len(node.subs) if not node.max_subs_picked else min(len(node.subs), node.max_subs_picked)
    sub_total = 0
    for sub in node.subs[:limit]:
        if sub.kind == "integration":
            child = _resolve_integration_node(sub.child_integration_id)
        else:
            child = _resolve_model_node(sub.model_id)
        sub_total += estimate_calls(child, depth + 1)
    return 2 + sub_total * node.rounds


__all__ = ["MODEL_PRICING", "cost_usd", "estimate_calls"]

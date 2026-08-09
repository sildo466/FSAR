"""One-shot probe: send `你好` to the active LLM the same way the real chat
flow does (system prompt + tool schemas registered), and print what comes back.

Goal: verify the post-fix AGENT_SYSTEM_PROMPT stops the model from inventing
tool calls on plain greetings.

Run: python tests/probe_greeting.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.core.prompts import AGENT_SYSTEM_PROMPT  # noqa: E402
from src.tools import create_default_registry  # noqa: E402
from src.utils.fsar_config import FsarConfig  # noqa: E402
from src.utils.llm_factory import cached_chat_completion, make_llm_client  # noqa: E402


def main() -> int:
    cfg = FsarConfig()
    active_id = cfg.get("llm.active", "")
    if not active_id:
        print("FAIL: no llm.active in fsar.yaml")
        return 1
    provider = cfg.get_llm_config(active_id)
    if not provider.get("api_key") or not provider.get("model"):
        print(f"FAIL: provider {active_id!r} missing api_key or model")
        return 1

    client = make_llm_client(active_id)
    registry = create_default_registry()
    tools = registry.get_tools_for_llm()

    messages = [
        {"role": "system", "content": AGENT_SYSTEM_PROMPT},
        {"role": "user", "content": "你好"},
    ]

    resp = cached_chat_completion(
        client,
        model=provider["model"],
        messages=messages,
        tools=tools if tools else None,
        tool_choice="auto" if tools else None,
        max_tokens=400,
    )

    msg = resp.choices[0].message
    finish = resp.choices[0].finish_reason
    usage = getattr(resp, "usage", None)
    print(f"[probe] model         = {provider['model']}")
    print(f"[probe] tools offered = {len(tools)}")
    print(f"[probe] finish_reason = {finish}")
    print(f"[probe] usage         = {dict(usage) if usage else None}")
    print(f"[probe] content       = {(msg.content or '').strip()!r}")
    print(f"[probe] tool_calls    = {[(t.function.name, t.function.arguments) for t in (msg.tool_calls or [])]!r}")

    invoked = bool(msg.tool_calls)
    greeted = bool((msg.content or "").strip())

    print()
    if invoked:
        print(f"FAIL: LLM called a tool on a plain greeting: "
              f"{[(t.function.name, t.function.arguments) for t in msg.tool_calls]}")
        return 1
    if not greeted:
        print("FAIL: LLM returned empty content")
        return 1
    print("OK: LLM replied directly without invoking any tool.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

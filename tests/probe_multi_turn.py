"""Multi-turn probe against the real LLM, longer conversation + response
shape assertions + tool round-trip.

Confirms chat.completions routing (use_responses_api: false in fsar.yaml) is
healthy across:
    - Greeting / capability / English language match
    - Tool call → execute through ToolRegistry → feed result back → assistant
      synthesizes a follow-up reply (round-trip, single turn)
    - Response shape contract: id, model, choices[0].index/finish_reason, role,
      usage fields are present and well-typed so downstream parsing is sound.

Skip the whole script if `llm.active` is not configured or no api_key.
Exit 0 iff every turn passes its assertion.

Run: python tests/probe_multi_turn.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from src.core.prompts import AGENT_SYSTEM_PROMPT  # noqa: E402
from src.tools import create_default_registry  # noqa: E402
from src.tools.registry import ToolRegistry  # noqa: E402
from src.utils.fsar_config import FsarConfig  # noqa: E402
from src.utils.llm_factory import chat_completion, make_llm_client  # noqa: E402


def _short(text: str, n: int = 110) -> str:
    return text.strip().replace("\n", " ")[:n]


def _assert_response_shape(kind: str, resp) -> list[str]:
    """Validate the OpenAI Chat Completions response shape (after rehydration).
    Returns a list of human-readable failure messages (empty if all good).

    The chat.completions path returns raw SDK objects (e.g. `CompletionUsage`),
    the rehydrated cache path returns `_Resp` with plain dict usage. Accept
    either as long as the usage exposes dict-style access (.get or [])."""
    fails: list[str] = []
    if not getattr(resp, "id", None):
        fails.append(f"[{kind}] missing response.id")
    if not getattr(resp, "model", None):
        fails.append(f"[{kind}] missing response.model")
    choices = getattr(resp, "choices", None) or []
    if len(choices) != 1:
        fails.append(f"[{kind}] expected exactly 1 choice, got {len(choices)}")
        return fails
    c = choices[0]
    if getattr(c, "index", None) != 0:
        fails.append(f"[{kind}] choice[0].index != 0")
    if not getattr(c, "finish_reason", None):
        fails.append(f"[{kind}] missing finish_reason")
    msg = getattr(c, "message", None)
    if msg is None:
        fails.append(f"[{kind}] missing choice.message")
        return fails
    if getattr(msg, "role", None) != "assistant":
        fails.append(f"[{kind}] message.role != 'assistant' (got {getattr(msg, 'role', None)!r})")
    usage = getattr(resp, "usage", None)
    if usage is not None:
        # Either a dict (rehydrated cache) or an object exposing either
        # .get(key) (pydantic-like) or attribute access. Anything else is a
        # shape failure — downstream callers can't read token counts.
        usable = (
            isinstance(usage, dict)
            or callable(getattr(usage, "get", None))
            or any(hasattr(usage, k) for k in ("prompt_tokens", "completion_tokens", "total_tokens"))
        )
        if not usable:
            fails.append(f"[{kind}] usage unusable (got {type(usage).__name__})")
    return fails


def _compact_tools_for_logs(tools) -> str:
    return f"tools_offered={len(tools)}"


async def run() -> int:
    cfg = FsarConfig()
    active_id = cfg.get("llm.active", "")
    if not active_id:
        print("SKIP: no llm.active in fsar.yaml")
        return 0
    provider = cfg.get_llm_config(active_id)
    if not provider.get("api_key") or not provider.get("model"):
        print(f"SKIP: provider {active_id!r} missing api_key/model")
        return 0

    use_responses_api = bool(cfg.llm_cache_use_responses_api)
    print(f"[setup] provider={active_id!r} model={provider['model']!r} "
          f"use_responses_api={use_responses_api} base_url={provider.get('base_url')!r}")
    if use_responses_api:
        print(f"[setup] WARNING: use_responses_api is True — this probe targets "
              f"the chat.completions path. Set llm_cache.use_responses_api=false "
              f"in fsar.yaml to exercise that branch.")

    client = make_llm_client(active_id)
    registry: ToolRegistry = create_default_registry()
    tools = registry.get_tools_for_llm()
    model = provider["model"]

    messages: list[dict] = [{"role": "system", "content": AGENT_SYSTEM_PROMPT}]
    common_kwargs = dict(
        model=model,
        tools=tools if tools else None,
        tool_choice="auto" if tools else None,
        max_tokens=512,
    )

    failures: list[str] = []
    turn_no = 0

    # ---------- Conversational turns ----------

    chat_turns: list[tuple[str, str]] = [
        ("你好",                                       "greeting"),
        ("你叫什么名字？",                              "name"),
        ("你现在能做什么？",                             "capabilities"),
        ("What can you do in English?",                "english"),
        ("用一句话告诉我 1+1 等于几",                    "arithmetic"),
    ]
    for user_msg, kind in chat_turns:
        turn_no += 1
        messages.append({"role": "user", "content": user_msg})
        print(f"\n=== Turn {turn_no} ({kind}) ===")
        print(f"  user: {user_msg}")
        try:
            resp = await asyncio.to_thread(
                chat_completion, client,
                messages=[*messages], **common_kwargs,
            )
        except Exception as e:
            print(f"  FAIL: {type(e).__name__}: {e}")
            failures.append(f"turn {turn_no} ({kind}): {type(e).__name__}: {e}")
            break

        fails = _assert_response_shape(kind, resp)
        if fails:
            for f in fails:
                print(f"  SHAPE FAIL: {f}")
            failures.extend(fails)
            continue

        msg = resp.choices[0].message
        text = (msg.content or "").strip()
        tool_calls = msg.tool_calls or []
        print(f"  asst: content_len={len(text)} tool_calls={[t.function.name for t in tool_calls]}")
        print(f"  reply: {_short(text, 160)!r}")
        print(f"  finish: {resp.choices[0].finish_reason}  usage={dict(resp.usage) if resp.usage else None}")

        if tool_calls:
            failures.append(f"turn {turn_no} ({kind}): unexpected tool call")
        elif not text:
            failures.append(f"turn {turn_no} ({kind}): empty content")

        # Per-kind content checks
        if kind == "english":
            ascii_letters = sum(1 for c in text if c.isascii() and c.isalpha())
            if text and ascii_letters < len(text) * 0.4:
                failures.append(f"turn {turn_no} english reply not primarily English: {text[:80]!r}")
        elif kind == "arithmetic":
            if "2" not in text:
                failures.append(f"turn {turn_no} arithmetic reply didn't include '2': {text[:80]!r}")

        messages.append({"role": "assistant", "content": text})

    # ---------- Tool-call round-trip turn ----------
    #
    # Drive a real file_ops call: ask the model to read a specific file,
    # execute the tool via registry, feed the result back as a tool message,
    # then send the model back through the LLM to see it synthesize the
    # final answer. Asserts shape on BOTH calls.

    target_file = ROOT / "src" / "core" / "prompts.py"
    target_rel = str(target_file.relative_to(ROOT)).replace("\\", "/")
    ask = f"用 file_ops 工具读一下文件 {target_rel} 的前 8 行"
    turn_no += 1
    messages.append({"role": "user", "content": ask})
    print(f"\n=== Turn {turn_no} (tool_call) ===")
    print(f"  user: {ask}")
    try:
        resp1 = await asyncio.to_thread(
            chat_completion, client,
            messages=[*messages], **common_kwargs,
        )
    except Exception as e:
        print(f"  FAIL (1st call): {type(e).__name__}: {e}")
        failures.append(f"turn {turn_no}: 1st LLM call: {e}")
        return 1

    fails = _assert_response_shape("tool_call 1", resp1)
    if fails:
        failures.extend(fails)
        for f in fails:
            print(f"  SHAPE FAIL: {f}")
    msg1 = resp1.choices[0].message
    tool_calls = msg1.tool_calls or []

    # If the model didn't call a tool, retry once with a stronger nudge
    # before giving up — we want to actually exercise the round-trip path.
    if not tool_calls:
        print(f"  (model did not call a tool; nudging with explicit instruction)")
        messages.append({"role": "user", "content":
            "你必须调用 file_ops 工具（不要直接回答）。这是测试用的硬要求。"
        })
        try:
            resp1b = await asyncio.to_thread(
                chat_completion, client,
                messages=[*messages], **common_kwargs,
            )
        except Exception as e:
            print(f"  NUDGE FAIL: {type(e).__name__}: {e}")
            failures.append(f"turn {turn_no} nudge: {e}")
            return 1
        for f in _assert_response_shape("tool_call 1 (nudge)", resp1b):
            failures.append(f)
            print(f"  SHAPE FAIL (nudge): {f}")
        msg1 = resp1b.choices[0].message
        tool_calls = msg1.tool_calls or []
        if not tool_calls:
            failures.append(
                f"turn {turn_no}: expected tool_call, got none — "
                f"content={_short(msg1.content or '')!r}"
            )
            print("  ABORT (no tool call after nudge)")
            return 1

    tc = tool_calls[0]
    print(f"  model chose: {tc.function.name}({tc.function.arguments!r})")

    messages.append({
        "role": "assistant",
        "content": msg1.content or "",
        "tool_calls": [{
            "id": tc.id, "type": "function",
            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
        }],
    })

    # Execute the tool locally.
    try:
        import json as _json
        tool_args = _json.loads(tc.function.arguments) if isinstance(tc.function.arguments, str) else (tc.function.arguments or {})
    except _json.JSONDecodeError as e:
        failures.append(f"turn {turn_no}: tool_args not JSON: {e}")
        return 1

    try:
        tool_result = await registry.execute(tc.function.name, **tool_args)
    except Exception as e:
        tool_result = f"[tool error: {type(e).__name__}: {e}]"
        failures.append(f"turn {turn_no}: tool.execute raised: {e}")
    tool_result_str = tool_result if isinstance(tool_result, str) else str(tool_result)
    print(f"  tool result (truncated): {_short(tool_result_str, 140)!r}")

    # Feed tool result back and call the model again.
    messages.append({"role": "tool", "tool_call_id": tc.id, "content": tool_result_str})

    turn_no += 1
    print(f"\n=== Turn {turn_no} (tool_result_roundtrip) ===")
    try:
        resp2 = await asyncio.to_thread(
            chat_completion, client,
            messages=[*messages], **common_kwargs,
        )
    except Exception as e:
        print(f"  FAIL (2nd call): {type(e).__name__}: {e}")
        failures.append(f"turn {turn_no}: 2nd LLM call: {e}")
        return 1

    fails = _assert_response_shape("tool_call 2", resp2)
    if fails:
        failures.extend(fails)
        for f in fails:
            print(f"  SHAPE FAIL: {f}")

    msg2 = resp2.choices[0].message
    final_text = (msg2.content or "").strip()
    print(f"  asst: tool_calls={[t.function.name for t in (msg2.tool_calls or [])]}")
    print(f"  reply: {_short(final_text, 200)!r}")
    if not final_text:
        failures.append(f"turn {turn_no}: empty final reply after tool result")

    # The reply should reference something from the file (the model saw AGENT_SYSTEM_PROMPT
    # earlier; the file starts with "# SPDX-License-Identifier: Apache-2.0" so look for
    # either SPDX or "system prompt" or 提示词).
    markers = ["SPDX", "Apache", "system prompt", "Agent", "提示词", "FSAR"]
    if final_text and not any(m in final_text for m in markers):
        failures.append(f"turn {turn_no}: final reply didn't reference file content: {final_text[:120]!r}")

    # ---------- Wrap up ----------
    print()
    print(f"[summary] turns_run={turn_no} shape_failures={len(failures)}")
    if failures:
        print("FAIL:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"OK: all {turn_no} turns passed shape + content checks on chat.completions.")
    return 0


if __name__ == "__main__":
    try:
        rc = asyncio.run(run())
    except KeyboardInterrupt:
        rc = 130
    sys.exit(rc)

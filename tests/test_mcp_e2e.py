"""End-to-end AI test: LLM picks an MCP tool from ToolRegistry, FSAR calls it.

Simulates the core loop in FSAR._handle_tool_task: load MCP, build tool
list, ask LLM to use the echo tool, verify the call lands and returns
the expected result.

Run:  python tests/test_mcp_e2e.py
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Re-use the FSAR config plumbing so .env is loaded
from src.utils.config import get_config  # noqa: E402
from src.mcp.manager import MCPManager  # noqa: E402
from src.tools.registry import ToolRegistry  # noqa: E402


async def run_e2e() -> int:
    cfg = get_config()
    llm_cfg = cfg.get_llm_config("primary")
    print(f"[e2e] LLM: {llm_cfg.get('provider')}/{llm_cfg.get('model')} @ {llm_cfg.get('base_url')[:60]}...")

    # --- Enable 'everything' MCP server temporarily ---
    cfg_path = ROOT / "config" / "mcp_servers.yaml"
    backup = cfg_path.with_suffix(".yaml.bak")
    shutil.copy(cfg_path, backup)
    text = cfg_path.read_text(encoding="utf-8")
    new_text = text.replace(
        """  - name: everything
    transport: stdio
    command: npx
    args: ["-y", "@modelcontextprotocol/server-everything"]
    risk_level: LOW
    enabled: false""",
        """  - name: everything
    transport: stdio
    command: npx
    args: ["-y", "@modelcontextprotocol/server-everything"]
    risk_level: LOW
    enabled: true""",
    )
    if new_text == text:
        print("[e2e] FAIL: could not enable 'everything'")
        return 1
    cfg_path.write_text(new_text, encoding="utf-8")

    rc = 0
    registry = ToolRegistry()
    manager = MCPManager(registry, config_path=cfg_path)

    try:
        # 1. Start MCP
        print("[e2e] starting MCP...")
        await manager.start()
        if "everything" not in manager.servers:
            print("[e2e] FAIL: 'everything' not started")
            return 1
        mcp_tools = [t for t in manager.list_visible_tools() if "echo" in t.name]
        if not mcp_tools:
            print("[e2e] FAIL: no echo tool found")
            return 1
        echo_tool_name = mcp_tools[0].name
        print(f"[e2e] MCP echo tool registered as: {echo_tool_name}")

        # 2. Build LLM tool list and call
        tools_for_llm = registry.get_tools_for_llm()
        echo_in_llm = [t for t in tools_for_llm if t["function"]["name"] == echo_tool_name]
        if not echo_in_llm:
            print(f"[e2e] FAIL: {echo_tool_name} not in registry.get_tools_for_llm()")
            return 1
        print(f"[e2e] tools count passed to LLM: {len(tools_for_llm)}")
        print(f"[e2e] echo tool schema: name={echo_in_llm[0]['function']['name']!r}, "
              f"params={list(echo_in_llm[0]['function']['parameters'].get('properties', {}).keys())}")

        # 3. Build OpenAI client (mirrors main.py workaround)
        import httpx
        import ssl as _ssl
        _ssl_ctx = _ssl.create_default_context()
        from openai import OpenAI
        llm = OpenAI(
            api_key=llm_cfg.get("api_key", ""),
            base_url=llm_cfg.get("base_url", ""),
            http_client=httpx.Client(verify=_ssl_ctx),
        )

        # 4. Ask the LLM to use the MCP echo tool
        prompt = (
            'Use the tool named "' + echo_tool_name + '" to echo back exactly '
            'the text "hello from e2e test". Do not respond with anything '
            'other than the tool call.'
        )
        print(f"[e2e] prompt: {prompt!r}")

        messages = [
            {"role": "system", "content": (
                "You must call the requested tool. Do not paraphrase the input."
            )},
            {"role": "user", "content": prompt},
        ]

        resp = llm.chat.completions.create(
            model=llm_cfg.get("model"),
            messages=messages,
            tools=tools_for_llm,
            tool_choice="auto",
            max_tokens=2048,
            temperature=0.0,
        )
        choice = resp.choices[0]
        msg = choice.message
        print(f"[e2e] LLM finish_reason: {choice.finish_reason}")
        print(f"[e2e] LLM text: {(msg.content or '')[:200]!r}")
        print(f"[e2e] LLM tool_calls: {len(msg.tool_calls or [])}")
        if not msg.tool_calls:
            print("[e2e] FAIL: LLM did not call any tool")
            rc = 1
            return rc

        tc = msg.tool_calls[0]
        print(f"[e2e] LLM chose tool: {tc.function.name!r}")
        try:
            args = json.loads(tc.function.arguments)
        except json.JSONDecodeError:
            args = {}
        print(f"[e2e] LLM args: {args}")
        if tc.function.name != echo_tool_name:
            print(f"[e2e] FAIL: LLM chose wrong tool {tc.function.name!r}")
            rc = 1
            return rc

        # 5. Execute via registry (this is what _execute_guarded does)
        print("[e2e] executing via registry...")
        result = await registry.execute(tc.function.name, **args)
        print(f"[e2e] registry.execute result: {result!r}")

        if "hello from e2e test" not in result:
            print(f"[e2e] FAIL: expected echoed text in result, got: {result!r}")
            rc = 1
            return rc

        # 6. Feed result back to LLM, get final answer (mirror loop in main.py)
        messages.append(msg)
        messages.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "content": result,
        })
        final = llm.chat.completions.create(
            model=llm_cfg.get("model"),
            messages=messages,
            max_tokens=2048,
            temperature=0.0,
        )
        final_text = final.choices[0].message.content or ""
        print(f"[e2e] final LLM reply: {final_text[:300]!r}")
        if "hello from e2e test" not in final_text:
            print("[e2e] NOTE: final LLM reply didn't include echoed text (acceptable, model commentary)")

        print("[e2e] OK: LLM selected MCP tool, registry executed it, result flowed back")
    except Exception as e:
        print(f"[e2e] FAIL: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        rc = 1
    finally:
        await manager.stop()
        shutil.move(backup, cfg_path)
        print("[e2e] restored config")

    return rc


if __name__ == "__main__":
    try:
        rc = asyncio.run(run_e2e())
    except KeyboardInterrupt:
        rc = 130
    sys.exit(rc)
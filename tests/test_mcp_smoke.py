"""End-to-end smoke test for FSAR LLM -> MCP integration.

Layer 1 (MCP layer, still uses tests/mcp_mock_server.py):
    start() -> list_tools() -> call_tool() -> adapter -> registry wiring.

Layer 2 (real API, NEW): drive the active LLM (configured via
    config/fsar.yaml `llm.active`) to invoke an MCP tool by name, then execute
    the call back through the registry and verify the result round-trips.

Requires:
    - `llm.active` set in config/fsar.yaml with a working api_key for that provider
    - tests/mcp_mock_server.py (the mock server itself)

If no active provider / missing api_key, layer 2 skips with a clear message
(layer 1 still runs and must pass). exit code 0 only when both layers pass
or layer 2 skips with a reason; layer 1 failures always exit non-zero.

Run:  python tests/test_mcp_smoke.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.mcp.client import MCPClient  # noqa: E402
from src.mcp.tool import MCPTool, _format_result  # noqa: E402
from src.tools.registry import ToolRegistry  # noqa: E402
from src.utils.fsar_config import FsarConfig  # noqa: E402
from src.utils.llm_factory import cached_chat_completion, make_llm_client  # noqa: E402


def find_python() -> str:
    return sys.executable


# ---------- Layer 1: MCP client + adapter + registry wiring ----------

async def layer1_mcp_basics() -> tuple[MCPClient, ToolRegistry]:
    """Low-level MCP smoke (mock server). Returns running client + registry
    pre-populated with all mock tools, for layer 2 to reuse."""
    py = find_python()
    server_script = str(ROOT / "tests" / "mcp_mock_server.py")

    print(f"[layer1] starting mock MCP server: {py} {server_script}")
    client = MCPClient(name="smoke", command=py, args=[server_script])
    await client.start()

    info = client.server_info
    print(f"[layer1] handshake OK: name={info.get('name')!r} version={info.get('version')!r}")
    if info.get("name") != "fsar-test-mock":
        await client.stop()
        raise AssertionError(f"expected server name 'fsar-test-mock', got {info.get('name')!r}")

    tools = await client.list_tools()
    names = sorted(t.name for t in tools)
    print(f"[layer1] list_tools returned: {names}")
    expected = {"echo", "add", "fail"}
    if set(names) != expected:
        await client.stop()
        raise AssertionError(f"expected {expected}, got {set(names)}")

    # call_tool: echo
    res = await client.call_tool("echo", {"text": "hello"})
    text = _format_result(res)
    print(f"[layer1] echo -> {text!r}")
    if "echo: hello" not in text:
        await client.stop()
        raise AssertionError(f"echo returned {text!r}")

    # call_tool: add
    res = await client.call_tool("add", {"a": 2, "b": 3})
    text = _format_result(res)
    print(f"[layer1] add(2,3) -> {text!r}")
    if text.strip() != "5":
        await client.stop()
        raise AssertionError(f"add returned {text!r}")

    # MCPTool adapter + registry wiring
    registry = ToolRegistry()
    for tdef in tools:
        adapted = MCPTool(server_name="smoke", tool_def=tdef, client=client, risk_level="LOW")
        registry.register(adapted)
    schemas = registry.get_tools_for_llm()
    if len(schemas) != 3:
        await client.stop()
        raise AssertionError(f"registry has {len(schemas)} schemas, expected 3")

    schema_names = sorted(s["function"]["name"] for s in schemas)
    print(f"[layer1] registry schema names: {schema_names}")
    print(f"[layer1] OK: 3 tools registered into ToolRegistry")
    return client, registry


# ---------- Layer 2: real LLM -> tool decision -> registry execute -> verify ----------

async def layer2_llm_end_to_end(registry: ToolRegistry) -> int:
    """Real LLM call: ask the active provider to call mcp__smoke__echo with a
    known probe string, execute the resulting tool call through the registry,
    and verify the result round-trips.

    Returns:
        0 on pass or graceful skip; non-zero on any failure.
    """
    print(f"\n[layer2] loading active LLM provider from config/fsar.yaml")
    try:
        cfg = FsarConfig()
        active_id = cfg.get("llm.active", "")
    except Exception as e:
        print(f"[layer2] FAIL: cannot load fsar.yaml: {e}")
        return 1

    if not active_id:
        print(f"[layer2] SKIP: no llm.active set; configure one in config/fsar.yaml")
        return 0

    try:
        provider = cfg.get_llm_config(active_id)
    except Exception as e:
        print(f"[layer2] FAIL: cannot read provider {active_id!r}: {e}")
        return 1

    if not provider.get("api_key"):
        print(f"[layer2] SKIP: provider {active_id!r} has no api_key")
        return 0
    if not provider.get("model"):
        print(f"[layer2] SKIP: provider {active_id!r} has no model")
        return 0

    print(f"[layer2] using provider {active_id!r} model={provider.get('model')!r} base_url={provider.get('base_url')!r}")

    try:
        client = make_llm_client(active_id)
    except Exception as e:
        print(f"[layer2] FAIL: make_llm_client raised: {e}")
        return 1

    probe_text = "hello from LLM"
    user_prompt = (
        f"Please call the MCP tool named `mcp__smoke__echo` exactly once with "
        f"the argument `text` set to the literal string {probe_text!r}, then "
        f"reply with the tool's output verbatim."
    )

    tools_for_llm = registry.get_tools_for_llm()
    print(f"[layer2] calling LLM with {len(tools_for_llm)} tool schemas...")
    try:
        resp = await asyncio.to_thread(
            cached_chat_completion,
            client,
            model=provider["model"],
            messages=[
                {"role": "system", "content": (
                    "You have access to MCP tools registered under the `mcp__smoke__` "
                    "prefix (echo, add, fail). When the user asks you to call a tool, "
                    "emit exactly one tool_call and pass the result back in your reply."
                )},
                {"role": "user", "content": user_prompt},
            ],
            tools=tools_for_llm,
            tool_choice="auto",
            max_tokens=512,
        )
    except Exception as e:
        print(f"[layer2] FAIL: LLM call raised: {type(e).__name__}: {e}")
        return 1

    message = resp.choices[0].message
    tool_calls = getattr(message, "tool_calls", None) or []
    if not tool_calls:
        print(f"[layer2] FAIL: LLM did not produce any tool call")
        print(f"[layer2]   content={getattr(message, 'content', '')!r}")
        return 1

    tc = tool_calls[0]
    fn_name = tc.function.name
    fn_args_raw = tc.function.arguments
    print(f"[layer2] LLM produced tool_call: {fn_name}({fn_args_raw!r})")

    if fn_name != "mcp__smoke__echo":
        print(f"[layer2] FAIL: expected mcp__smoke__echo, got {fn_name!r}")
        return 1

    try:
        fn_args = json.loads(fn_args_raw) if isinstance(fn_args_raw, str) else dict(fn_args_raw)
    except (json.JSONDecodeError, TypeError) as e:
        print(f"[layer2] FAIL: tool args not parseable: {e}")
        return 1

    if fn_args.get("text") != probe_text:
        print(f"[layer2] FAIL: expected text={probe_text!r}, got {fn_args.get('text')!r}")
        return 1
    print(f"[layer2] tool_call schema matches expectation")

    # Round-trip: execute the call through the registry and verify result.
    try:
        result = await registry.execute(fn_name, **fn_args)
    except Exception as e:
        print(f"[layer2] FAIL: registry.execute raised: {type(e).__name__}: {e}")
        return 1

    print(f"[layer2] registry.execute result: {result!r}")
    expected_marker = f"echo: {probe_text}"
    if expected_marker not in result:
        print(f"[layer2] FAIL: expected {expected_marker!r} in result")
        return 1

    print(f"[layer2] OK: LLM-driven MCP tool roundtrip succeeded")
    return 0


async def run_smoke() -> int:
    client: MCPClient | None = None
    try:
        client, registry = await layer1_mcp_basics()
        rc2 = await layer2_llm_end_to_end(registry)
        if rc2 != 0:
            return rc2
        print("\n[smoke] OK: all layers passed")
        return 0
    except AssertionError as e:
        print(f"[smoke] FAIL: {e}")
        return 1
    except Exception as e:
        print(f"[smoke] FAIL: unhandled {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        if client is not None:
            try:
                await client.stop()
            except Exception:
                pass


if __name__ == "__main__":
    try:
        rc = asyncio.run(run_smoke())
    except KeyboardInterrupt:
        rc = 130
    sys.exit(rc)

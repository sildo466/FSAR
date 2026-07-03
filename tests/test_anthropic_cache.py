"""Tests for Anthropic cache marker payload + factory dispatch."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.anthropic_cache import (
    AnthropicCacheLog,
    anthropic_response_to_openai_shape,
    convert_messages_to_anthropic,
    convert_tools_to_anthropic,
    digest_system_prompt,
    is_long_ttl_eligible,
    resolve_cache_control,
)


# --- TTL marker eligibility --------------------------------------------------

def test_long_ttl_eligibility_anthropic_direct():
    assert is_long_ttl_eligible("https://api.anthropic.com") is True
    assert is_long_ttl_eligible("https://api.anthropic.com/v1") is True


def test_long_ttl_eligibility_bedrock_ineligible():
    assert is_long_ttl_eligible("https://bedrock-runtime.us-east-1.amazonaws.com") is False


def test_long_ttl_eligibility_provider_override():
    assert is_long_ttl_eligible("", provider_override="anthropic") is True
    assert is_long_ttl_eligible("https://bedrock-runtime.us-east-1.amazonaws.com",
                                provider_override="anthropic") is True


def test_resolve_cache_control_short():
    m = resolve_cache_control(cache_retention="short", base_url="https://api.anthropic.com")
    assert m == {"type": "ephemeral"}


def test_resolve_cache_control_long_anthropic():
    m = resolve_cache_control(cache_retention="long", base_url="https://api.anthropic.com")
    assert m == {"type": "ephemeral", "ttl": "1h"}


def test_resolve_cache_control_long_bedrock():
    m = resolve_cache_control(cache_retention="long", base_url="https://bedrock-runtime.us-east-1.amazonaws.com")
    # Bedrock ineligible → no ttl:1h marker, ephemeral only.
    assert m == {"type": "ephemeral"}


def test_resolve_cache_control_none():
    assert resolve_cache_control(cache_retention="none") is None


# --- Payload conversion ------------------------------------------------------

def test_convert_messages_extracts_system_and_marks_cache():
    msgs = [
        {"role": "system", "content": "you are helpful"},
        {"role": "user", "content": "hi"},
    ]
    sys_blocks, m = convert_messages_to_anthropic(
        msgs, cache_control={"type": "ephemeral", "ttl": "1h"}
    )
    assert sys_blocks is not None and len(sys_blocks) == 1
    assert sys_blocks[0]["text"] == "you are helpful"
    assert sys_blocks[0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
    # Trailing user message becomes a content block list with cache_control
    assert isinstance(m[-1]["content"], list)
    assert m[-1]["content"][0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}


def test_convert_messages_no_system():
    msgs = [{"role": "user", "content": "hi"}]
    sys_blocks, m = convert_messages_to_anthropic(msgs, cache_control={"type": "ephemeral"})
    assert sys_blocks is None
    assert isinstance(m[-1]["content"], list)
    assert m[-1]["content"][0]["cache_control"] == {"type": "ephemeral"}


def test_convert_messages_concatenates_multiple_system_blocks():
    msgs = [
        {"role": "system", "content": "first"},
        {"role": "system", "content": "second"},
        {"role": "user", "content": "hi"},
    ]
    sys_blocks, _ = convert_messages_to_anthropic(msgs, cache_control={"type": "ephemeral"})
    assert sys_blocks is not None and len(sys_blocks) == 1
    assert "first" in sys_blocks[0]["text"] and "second" in sys_blocks[0]["text"]


def test_convert_messages_assistant_tool_calls_become_tool_use_blocks():
    msgs = [
        {"role": "user", "content": "do it"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "tc_1", "function": {"name": "foo", "arguments": '{"x":1}'}},
        ]},
    ]
    _, m = convert_messages_to_anthropic(msgs, cache_control=None)
    assert m[-1]["role"] == "assistant"
    blocks = m[-1]["content"]
    assert any(b.get("type") == "tool_use" for b in blocks)


def test_convert_messages_tool_result_becomes_user_tool_result():
    msgs = [
        {"role": "user", "content": "do it"},
        {"role": "assistant", "tool_calls": [{"id": "tc_1", "function": {"name": "foo", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "tc_1", "content": "result"},
    ]
    _, m = convert_messages_to_anthropic(msgs, cache_control=None)
    tool_block = m[-1]["content"][0]
    assert tool_block["type"] == "tool_result"
    assert tool_block["tool_use_id"] == "tc_1"


def test_convert_tools_translates_openai_shape():
    tools = [{"type": "function",
              "function": {"name": "foo", "description": "d",
                           "parameters": {"type": "object", "properties": {"x": {"type": "number"}}}}}]
    out = convert_tools_to_anthropic(tools)
    assert out == [{"name": "foo", "description": "d",
                    "input_schema": {"type": "object", "properties": {"x": {"type": "number"}}}}]


def test_convert_tools_empty():
    assert convert_tools_to_anthropic(None) is None
    assert convert_tools_to_anthropic([]) is None


# --- Response normalization --------------------------------------------------

class _TextBlock:
    type = "text"
    text = "hello"


class _ToolUseBlock:
    type = "tool_use"
    id = "tu_1"
    name = "foo"
    input = {"a": 1}


class _AnthropicResp:
    id = "msg_01"
    model = "claude-3-5-sonnet"
    stop_reason = "tool_use"
    content = [_TextBlock(), _ToolUseBlock()]


def test_response_normalization_text_only():
    class _R:
        id = "x"
        model = "claude-3-5-sonnet"
        stop_reason = "end_turn"
        content = [_TextBlock()]
    out = anthropic_response_to_openai_shape(_R(), "claude-3-5-sonnet")
    assert out["choices"][0]["message"]["content"] == "hello"
    assert out["choices"][0]["message"]["tool_calls"] is None
    assert out["choices"][0]["finish_reason"] == "end_turn"


def test_response_normalization_tool_use():
    out = anthropic_response_to_openai_shape(_AnthropicResp(), "claude-3-5-sonnet")
    text, tools = out["choices"][0]["message"]["content"], out["choices"][0]["message"]["tool_calls"]
    assert "hello" in text
    assert tools is not None and len(tools) == 1
    assert tools[0]["function"]["name"] == "foo"
    assert '"a": 1' in tools[0]["function"]["arguments"]
    assert out["choices"][0]["finish_reason"] == "tool_use"


# --- Cache log observability -------------------------------------------------

def test_cache_log_append_and_last_for():
    with tempfile.TemporaryDirectory() as d:
        log = AnthropicCacheLog(db_path=str(Path(d) / "c.db"))
        log.append(provider="anthropic", model_id="claude-3-5-sonnet",
                   cache_retention="long", system_prompt="you are helpful")
        log.append(provider="anthropic", model_id="claude-3-5-sonnet",
                   cache_retention="long", system_prompt="you are helpful")
        ts = log.last_for(provider="anthropic", model_id="claude-3-5-sonnet")
        assert ts is not None
        assert log.stats()["rows"] == 2


def test_cache_log_isolates_per_provider_model():
    with tempfile.TemporaryDirectory() as d:
        log = AnthropicCacheLog(db_path=str(Path(d) / "c.db"))
        log.append(provider="anthropic", model_id="haiku", cache_retention="short", system_prompt="a")
        log.append(provider="anthropic", model_id="sonnet", cache_retention="short", system_prompt="b")
        assert log.last_for(provider="anthropic", model_id="haiku") is not None
        assert log.last_for(provider="anthropic", model_id="sonnet") is not None
        assert log.last_for(provider="anthropic", model_id="missing") is None


# --- Factory dispatch (smoke) ------------------------------------------------

def test_factory_dispatches_to_anthropic(monkeypatch=None):
    """Smoke test: client.chat.completions.create is NEVER called when family=anthropic."""
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from src.utils import llm_factory
    from src.utils.llm_factory import chat_completion_anthropic, make_anthropic_client

    # Replace the singleton cache with a stub.
    class _StubCache:
        def __init__(self):
            self.writes = []
        def get(self, payload):
            return None
        def put(self, payload, response, cache_enabled=True):
            self.writes.append(payload)

    cache = _StubCache()
    # Build a fake Anthropic client + force the factory to use it.
    fake_resp = _AnthropicResp()

    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_resp

    llm_factory._ANTHROPIC_CLIENTS["primary"] = fake_client
    try:
        out = chat_completion_anthropic(
            messages=[
                {"role": "system", "content": "you are helpful"},
                {"role": "user", "content": "hi"},
            ],
            model="claude-3-5-sonnet",
            cache=cache,
            cache_enabled=True,
            cache_retention="long",
            base_url="https://api.anthropic.com",
            max_tokens=1024,
        )
        assert fake_client.messages.create.called, "messages.create should have been called"
        kwargs = fake_client.messages.create.call_args.kwargs
        assert "system" in kwargs
        assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
        # Response normalized back to OpenAI shape.
        assert out.choices[0].message.content == "hello"
        # L2 cache write happened.
        assert len(cache.writes) == 1
    finally:
        del llm_factory._ANTHROPIC_CLIENTS["primary"]

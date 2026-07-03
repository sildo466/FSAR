"""Tests for src/utils/responses_compat.py — pure conversion functions."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.responses_compat import (
    build_responses_kwargs,
    extract_system_prompt,
    messages_to_responses_input,
    resolve_prompt_cache_retention,
    responses_to_chat_shape,
    tool_choice_responses,
    tools_to_responses_tools,
)


# --- extract_system_prompt ---------------------------------------------------

def test_extract_system_prompt_single():
    msgs = [{"role": "system", "content": "you are helpful"}, {"role": "user", "content": "hi"}]
    assert extract_system_prompt(msgs) == "you are helpful"


def test_extract_system_prompt_multiple():
    msgs = [
        {"role": "system", "content": "first"},
        {"role": "system", "content": "second"},
        {"role": "user", "content": "hi"},
    ]
    out = extract_system_prompt(msgs)
    assert "first" in out and "second" in out


def test_extract_system_prompt_stops_at_non_system():
    msgs = [
        {"role": "system", "content": "before"},
        {"role": "user", "content": "middle"},
        {"role": "system", "content": "after (skipped)"},
    ]
    assert extract_system_prompt(msgs) == "before"


def test_extract_system_prompt_empty():
    assert extract_system_prompt([]) == ""
    assert extract_system_prompt([{"role": "user", "content": "hi"}]) == ""


# --- messages_to_responses_input ---------------------------------------------

def test_input_user_string():
    msgs = [{"role": "user", "content": "hello"}]
    out = messages_to_responses_input(msgs)
    assert len(out) == 1
    assert out[0]["role"] == "user"
    assert out[0]["content"] == [{"type": "input_text", "text": "hello"}]


def test_input_assistant_string_uses_output_text():
    msgs = [{"role": "assistant", "content": "reply"}]
    out = messages_to_responses_input(msgs)
    assert out[0]["content"] == [{"type": "output_text", "text": "reply"}]


def test_input_system_stripped():
    msgs = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]
    out = messages_to_responses_input(msgs)
    assert len(out) == 1
    assert out[0]["role"] == "user"


def test_input_assistant_tool_call():
    msgs = [
        {"role": "user", "content": "do it"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "tc_1", "function": {"name": "foo", "arguments": '{"x":1}'}},
        ]},
    ]
    out = messages_to_responses_input(msgs)
    fc = [item for item in out if item.get("type") == "function_call"]
    assert len(fc) == 1
    assert fc[0]["name"] == "foo"
    assert '"x": 1' in fc[0]["arguments"]


def test_input_tool_message_becomes_function_call_output():
    msgs = [
        {"role": "user", "content": "do it"},
        {"role": "assistant", "tool_calls": [{"id": "tc_1", "function": {"name": "foo", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "tc_1", "content": "result"},
    ]
    out = messages_to_responses_input(msgs)
    fco = [item for item in out if item.get("type") == "function_call_output"]
    assert len(fco) == 1
    assert fco[0]["call_id"] == "tc_1"
    assert fco[0]["output"] == "result"


def test_input_image_part():
    msgs = [{"role": "user", "content": [
        {"type": "text", "text": "look"},
        {"type": "image_url", "image_url": {"url": "https://x/a.png"}},
    ]}]
    out = messages_to_responses_input(msgs)
    items = out[0]["content"]
    types = [p["type"] for p in items]
    assert "input_text" in types
    assert "input_image" in types


# --- tools_to_responses_tools ------------------------------------------------

def test_tools_drops_function_envelope():
    tools = [{"type": "function",
              "function": {"name": "foo", "description": "d",
                           "parameters": {"type": "object", "properties": {"x": {"type": "number"}}}}}]
    out = tools_to_responses_tools(tools)
    assert out == [{"type": "function", "name": "foo", "description": "d",
                    "parameters": {"type": "object", "properties": {"x": {"type": "number"}}}}]


def test_tools_empty():
    assert tools_to_responses_tools(None) is None
    assert tools_to_responses_tools([]) is None


def test_tools_preserves_non_function_types():
    tools = [{"type": "web_search"}]
    out = tools_to_responses_tools(tools)
    assert out == [{"type": "web_search"}]


# --- tool_choice_responses ---------------------------------------------------

def test_tool_choice_strings():
    assert tool_choice_responses("auto") == "auto"
    assert tool_choice_responses("none") == "none"
    assert tool_choice_responses(None) is None
    assert tool_choice_responses("") is None


def test_tool_choice_named():
    tc = {"type": "function", "function": {"name": "foo"}}
    out = tool_choice_responses(tc)
    assert out == {"type": "function", "name": "foo"}


# --- resolve_prompt_cache_retention ------------------------------------------

def test_prompt_cache_retention_long_openai():
    assert resolve_prompt_cache_retention("long", "https://api.openai.com") == "24h"


def test_prompt_cache_retention_long_other_relay():
    assert resolve_prompt_cache_retention("long", "https://yunwu.ai/v1") is None


def test_prompt_cache_retention_short():
    assert resolve_prompt_cache_retention("short", "https://api.openai.com") is None
    assert resolve_prompt_cache_retention("short", "https://yunwu.ai/v1") is None


def test_prompt_cache_retention_none():
    assert resolve_prompt_cache_retention("none", "https://api.openai.com") is None


# --- build_responses_kwargs --------------------------------------------------

def test_build_kwargs_basic():
    payload = {"model": "m", "messages": [
        {"role": "system", "content": "be helpful"},
        {"role": "user", "content": "hi"},
    ]}
    out = build_responses_kwargs(
        payload=payload,
        system_prompt="be helpful",
        session_id="sess-1",
        cache_retention="short",
        base_url="https://yunwu.ai/v1",
    )
    assert out["model"] == "m"
    assert out["instructions"] == "be helpful"
    assert out["input"] == [{"role": "user", "content": [{"type": "input_text", "text": "hi"}]}]
    assert out["prompt_cache_key"] == "sess-1"
    assert "prompt_cache_retention" not in out


def test_build_kwargs_long_only_openai():
    payload = {"model": "m", "messages": [{"role": "user", "content": "hi"}]}
    out = build_responses_kwargs(
        payload=payload,
        system_prompt="",
        session_id="sess-1",
        cache_retention="long",
        base_url="https://api.openai.com",
    )
    assert out["prompt_cache_retention"] == "24h"

    out2 = build_responses_kwargs(
        payload=payload,
        system_prompt="",
        session_id="sess-1",
        cache_retention="long",
        base_url="https://yunwu.ai/v1",
    )
    assert "prompt_cache_retention" not in out2


def test_build_kwargs_no_session_id_omits_cache_key():
    payload = {"model": "m", "messages": [{"role": "user", "content": "hi"}]}
    out = build_responses_kwargs(
        payload=payload,
        system_prompt="",
        session_id=None,
        cache_retention="short",
        base_url="",
    )
    assert "prompt_cache_key" not in out


def test_build_kwargs_retention_none_omits_cache_key():
    payload = {"model": "m", "messages": [{"role": "user", "content": "hi"}]}
    out = build_responses_kwargs(
        payload=payload,
        system_prompt="",
        session_id="sess-1",
        cache_retention="none",
        base_url="",
    )
    assert "prompt_cache_key" not in out


def test_build_kwargs_temperature_max_tokens():
    payload = {"model": "m", "messages": [], "temperature": 0.7, "max_tokens": 256}
    out = build_responses_kwargs(
        payload=payload, system_prompt="", session_id=None,
        cache_retention="short", base_url="",
    )
    assert out["temperature"] == 0.7
    assert out["max_output_tokens"] == 256


# --- responses_to_chat_shape -------------------------------------------------

def test_chat_shape_text_only():
    resp = {
        "id": "resp_1",
        "object": "response",
        "model": "m",
        "status": "completed",
        "output": [
            {"type": "message", "role": "assistant",
             "content": [{"type": "output_text", "text": "hello"}]},
        ],
    }
    out = responses_to_chat_shape(resp, "m")
    assert out["choices"][0]["message"]["content"] == "hello"
    assert out["choices"][0]["message"]["tool_calls"] is None
    assert out["choices"][0]["finish_reason"] == "stop"


def test_chat_shape_function_call():
    resp = {
        "id": "resp_2",
        "model": "m",
        "status": "completed",
        "output": [
            {"type": "function_call", "call_id": "call_1", "name": "foo", "arguments": '{"a":1}'},
        ],
    }
    out = responses_to_chat_shape(resp, "m")
    tc = out["choices"][0]["message"]["tool_calls"]
    assert tc is not None and len(tc) == 1
    assert tc[0]["function"]["name"] == "foo"
    assert '"a": 1' in tc[0]["function"]["arguments"]


def test_chat_shape_mixed():
    resp = {
        "id": "resp_3",
        "model": "m",
        "status": "completed",
        "output": [
            {"type": "message", "role": "assistant",
             "content": [{"type": "output_text", "text": "I'll call foo"}]},
            {"type": "function_call", "call_id": "call_2", "name": "foo", "arguments": "{}"},
        ],
    }
    out = responses_to_chat_shape(resp, "m")
    msg = out["choices"][0]["message"]
    assert "I'll call foo" in msg["content"]
    assert msg["tool_calls"] is not None


def test_chat_shape_status_incomplete_maps_to_length():
    resp = {
        "id": "r", "model": "m", "status": "incomplete",
        "output": [{"type": "message", "role": "assistant",
                    "content": [{"type": "output_text", "text": "partial"}]}],
    }
    out = responses_to_chat_shape(resp, "m")
    assert out["choices"][0]["finish_reason"] == "length"


def test_chat_shape_failed_with_error():
    resp = {
        "id": "r", "model": "m", "status": "failed",
        "output": [],
        "error": {"message": "boom"},
    }
    out = responses_to_chat_shape(resp, "m")
    assert "boom" in out["choices"][0]["message"]["content"]


def test_chat_shape_accepts_object():
    """Some SDKs return pydantic-like objects rather than dicts."""

    class _Msg:
        type = "message"
        role = "assistant"
        content = [{"type": "output_text", "text": "hi"}]

    class _Resp:
        id = "r"
        model = "m"
        status = "completed"
        output = [_Msg()]
        output_text = "hi"
        usage = {}

    out = responses_to_chat_shape(_Resp(), "m")
    assert out["choices"][0]["message"]["content"] == "hi"
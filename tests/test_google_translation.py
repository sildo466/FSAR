# SPDX-License-Identifier: MIT
from src.providers.llm.google import from_gemini_response, to_gemini_request


def test_to_gemini_request_basic_messages():
    out = to_gemini_request(
        messages=[
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
        ],
        tools=None,
        thinking_payload=None,
        max_tokens=512,
    )
    assert out["systemInstruction"]["parts"][0]["text"] == "You are helpful."
    assert out["contents"] == [{"role": "user", "parts": [{"text": "Hello"}]}]
    assert out["generationConfig"]["maxOutputTokens"] == 512
    assert "thinkingConfig" not in out["generationConfig"]


def test_to_gemini_request_with_thinking_payload():
    payload = {"generationConfig": {"thinkingConfig": {"thinkingLevel": "HIGH"}}}
    out = to_gemini_request(
        messages=[{"role": "user", "content": "Hi"}],
        tools=None,
        thinking_payload=payload,
        max_tokens=1024,
    )
    assert out["generationConfig"]["thinkingConfig"]["thinkingLevel"] == "HIGH"


def test_to_gemini_request_with_tools():
    tools = [{
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the weather",
            "parameters": {"type": "object", "properties": {"city": {"type": "string"}}},
        },
    }]
    out = to_gemini_request(
        messages=[{"role": "user", "content": "Weather?"}],
        tools=tools,
        thinking_payload=None,
        max_tokens=256,
    )
    assert out["tools"][0]["functionDeclarations"][0]["name"] == "get_weather"
    assert "parameters" in out["tools"][0]["functionDeclarations"][0]


def test_to_gemini_request_tool_message_round_trip():
    messages = [
        {"role": "user", "content": "Weather?"},
        {"role": "assistant", "content": "", "tool_calls": [{
            "id": "call_abc",
            "type": "function",
            "function": {"name": "get_weather", "arguments": '{"city": "SF"}'},
        }]},
        {"role": "tool", "tool_call_id": "call_abc", "content": '{"temp": 68}'},
    ]
    out = to_gemini_request(messages=messages, tools=None, thinking_payload=None, max_tokens=256)
    assert out["contents"][1]["role"] == "model"
    assert out["contents"][1]["parts"][0]["functionCall"]["name"] == "get_weather"
    assert out["contents"][2]["role"] == "user"
    assert out["contents"][2]["parts"][0]["functionResponse"]["name"] == "get_weather"
    assert out["contents"][2]["parts"][0]["functionResponse"]["response"] == {"temp": 68}


def test_from_gemini_response_text_only():
    gemini = {
        "candidates": [{"content": {"parts": [{"text": "Hello back"}]}, "finishReason": "STOP"}],
        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5, "totalTokenCount": 15},
    }
    out = from_gemini_response(gemini)
    assert out["content"] == "Hello back"
    assert out["reasoning_content"] == ""
    assert out["tool_calls"] == []
    assert out["finish_reason"] == "stop"
    assert out["usage"]["totalTokenCount"] == 15


def test_from_gemini_response_with_thinking():
    gemini = {
        "candidates": [{"content": {"parts": [
            {"thought": True, "text": "Reasoning about..."},
            {"text": "Answer"},
        ]}, "finishReason": "STOP"}],
        "usageMetadata": {"totalTokenCount": 20},
    }
    out = from_gemini_response(gemini)
    assert out["reasoning_content"] == "Reasoning about..."
    assert out["content"] == "Answer"


def test_from_gemini_response_with_tool_call():
    gemini = {
        "candidates": [{"content": {"parts": [
            {"functionCall": {"name": "get_weather", "args": {"city": "SF"}}}
        ]}, "finishReason": "STOP"}],
        "usageMetadata": {"totalTokenCount": 30},
    }
    out = from_gemini_response(gemini)
    assert len(out["tool_calls"]) == 1
    assert out["tool_calls"][0]["function"]["name"] == "get_weather"
    assert out["tool_calls"][0]["function"]["arguments"] == '{"city": "SF"}'
    assert out["tool_calls"][0]["id"].startswith("gemini-")


def test_from_gemini_response_finish_reason_mapping():
    max_tokens = {"candidates": [{"content": {"parts": []}, "finishReason": "MAX_TOKENS"}]}
    safety = {"candidates": [{"content": {"parts": []}, "finishReason": "SAFETY"}]}
    assert from_gemini_response(max_tokens)["finish_reason"] == "length"
    assert from_gemini_response(safety)["finish_reason"] == "content_filter"

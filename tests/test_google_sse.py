# SPDX-License-Identifier: MIT
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

from src.providers.llm.google import google_chat_completion


def _sse_lines(events: list[dict]) -> list[str]:
    lines = []
    for event in events:
        lines.append(f"data: {json.dumps(event)}")
        lines.append("")
    return lines


class FakeStream:
    def __init__(self, lines: list[str]):
        self._lines = iter(lines)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._lines)
        except StopIteration:
            raise StopAsyncIteration


def _streaming_response(events: list[dict]):
    response = MagicMock()
    response.status_code = 200
    response.raise_for_status = MagicMock()
    response.aclose = AsyncMock()
    response.aiter_lines = lambda: FakeStream(_sse_lines(events))
    return response


async def _collect(events: list[dict]) -> list[dict]:
    send_mock = AsyncMock(return_value=_streaming_response(events))
    with patch("httpx.AsyncClient.send", new=send_mock):
        chunks = [chunk async for chunk in google_chat_completion(
            api_key="test",
            model="gemini-3-pro",
            messages=[{"role": "user", "content": "Hi"}],
            tools=None,
            thinking_payload=None,
            max_tokens=256,
            stream=True,
        )]
    assert send_mock.await_args.kwargs["stream"] is True
    return chunks


def test_streaming_yields_text_deltas():
    events = [
        {"candidates": [{"content": {"parts": [{"text": "Hello"}]}}]},
        {"candidates": [{"content": {"parts": [{"text": " world"}]}}]},
        {"candidates": [{"content": {"parts": [{"text": "!"}]}, "finishReason": "STOP"}]},
    ]
    chunks = asyncio.run(_collect(events))
    assert any(chunk.get("delta") == "Hello" for chunk in chunks)
    assert any(chunk.get("delta") == " world" for chunk in chunks)
    assert any(chunk.get("delta") == "!" for chunk in chunks)
    assert any(chunk.get("done") is True for chunk in chunks)


def test_streaming_thinking_parts_separated():
    events = [
        {"candidates": [{"content": {"parts": [{"thought": True, "text": "Let me think..."}]}}]},
        {"candidates": [{"content": {"parts": [{"text": "Final answer"}]}}]},
        {"candidates": [{"content": {"parts": []}, "finishReason": "STOP"}]},
    ]
    chunks = asyncio.run(_collect(events))
    thinking = "".join(chunk.get("thinking", "") for chunk in chunks)
    deltas = "".join(chunk.get("delta", "") for chunk in chunks)
    assert thinking == "Let me think..."
    assert deltas == "Final answer"


def test_streaming_tool_call_aggregated_at_end():
    events = [
        {"candidates": [{"content": {"parts": [
            {"functionCall": {"name": "get_weather", "args": {"city": "SF"}}}
        ]}}]},
        {"candidates": [{"content": {"parts": []}, "finishReason": "STOP"}]},
    ]
    chunks = asyncio.run(_collect(events))
    tool_calls = [
        tool_call
        for chunk in chunks
        for tool_call in chunk.get("tool_calls", [])
    ]
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["name"] == "get_weather"

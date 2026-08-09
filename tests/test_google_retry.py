# SPDX-License-Identifier: MIT
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.providers.llm.google import google_chat_completion


def _mock_response(status_code: int, json_body: dict | None = None):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_body or {}
    response.raise_for_status = MagicMock()
    if status_code >= 400:
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "boom", request=MagicMock(), response=response,
        )
    return response


def _complete(post_mock: AsyncMock):
    with patch("httpx.AsyncClient.post", new=post_mock):
        return asyncio.run(google_chat_completion(
            api_key="test",
            model="gemini-3-pro",
            messages=[{"role": "user", "content": "Hi"}],
            tools=None,
            thinking_payload=None,
            max_tokens=256,
            stream=False,
        ))


def test_non_streaming_success():
    body = {"candidates": [{"content": {"parts": [{"text": "OK"}]}, "finishReason": "STOP"}]}
    result = _complete(AsyncMock(return_value=_mock_response(200, body)))
    assert result["content"] == "OK"
    assert result["finish_reason"] == "stop"


def test_429_retries_once_then_succeeds():
    body = {"candidates": [{"content": {"parts": [{"text": "OK"}]}, "finishReason": "STOP"}]}
    post_mock = AsyncMock(side_effect=[_mock_response(429), _mock_response(200, body)])
    result = _complete(post_mock)
    assert post_mock.call_count == 2
    assert result["content"] == "OK"


def test_500_retries_once_then_succeeds():
    body = {"candidates": [{"content": {"parts": [{"text": "OK"}]}, "finishReason": "STOP"}]}
    post_mock = AsyncMock(side_effect=[_mock_response(500), _mock_response(200, body)])
    _complete(post_mock)
    assert post_mock.call_count == 2


def test_400_no_retry():
    post_mock = AsyncMock(return_value=_mock_response(400))
    with pytest.raises(httpx.HTTPStatusError):
        _complete(post_mock)
    assert post_mock.call_count == 1


def test_429_retries_exhausted_raises():
    post_mock = AsyncMock(return_value=_mock_response(429))
    with pytest.raises(httpx.HTTPStatusError):
        _complete(post_mock)
    assert post_mock.call_count == 2

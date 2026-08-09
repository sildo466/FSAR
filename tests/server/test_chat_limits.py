# SPDX-License-Identifier: MIT
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src.server.chat_engine import ChatEngine
from src.server.handlers import chat
from src.server.handlers import provider as provider_handler


def test_history_keeps_latest_messages_within_configured_budget():
    history = [
        {"role": "user", "content": "old" * 100},
        {"role": "assistant", "content": "middle" * 100},
        {"role": "user", "content": "latest"},
    ]

    fitted = ChatEngine._fit_history("system", history, 1100, 1000)

    assert fitted == [{"role": "user", "content": "latest"}]


def test_agent_compaction_preserves_latest_user_and_tool_pair():
    tool_call = SimpleNamespace(content=None, tool_calls=["call"])
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "old" * 100},
        {"role": "assistant", "content": "old reply" * 100},
        {"role": "user", "content": "current task"},
        tool_call,
        {"role": "tool", "tool_call_id": "1", "content": "result"},
    ]

    fitted = ChatEngine._fit_agent_messages(messages, 1100, 1000)

    assert fitted[1]["content"] == "current task"
    assert fitted[-2:] == [tool_call, messages[-1]]


def test_cancel_stops_the_socket_chat_task():
    async def run():
        previous_engine = chat._engine
        previous_tasks = dict(chat._tasks)
        started = asyncio.Event()
        cancelled = asyncio.Event()

        class Engine:
            async def handle_send(self, *args):
                started.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()

            def cancel(self):
                pass

        ws = object()
        chat.set_engine(Engine())
        try:
            await chat.dispatch(ws, {"type": "chat.send", "content": "hello"})
            await started.wait()
            await chat.dispatch(ws, {"type": "chat.cancel"})
            await asyncio.wait_for(cancelled.wait(), timeout=1)
        finally:
            chat._tasks.clear()
            chat._tasks.update(previous_tasks)
            chat._engine = previous_engine

    asyncio.run(run())


def test_fetch_models_accepts_models_name_shape():
    async def run():
        fake_response = AsyncMock(status_code=200, json=lambda: {"models": [{"name": "model-a"}]})
        with patch("src.server.handlers.provider.httpx.AsyncClient") as client_class:
            client = AsyncMock()
            client.get.return_value = fake_response
            client_class.return_value.__aenter__.return_value = client
            return await provider_handler.provider_fetch_models(
                preset_id="openai",
                base_url="https://api.example.com/v1",
                api_key="sk-test",
            )

    result = asyncio.run(run())
    assert result["ok"] is True
    assert result["models"] == ["model-a"]

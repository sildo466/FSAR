# SPDX-License-Identifier: MIT
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from src.server import chat_engine as ce
from src.server.chat_engine import ChatEngine


class FakeWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send_json(self, message: dict) -> None:
        self.messages.append(message)


def _chunk(text: str):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text))])


def _engine() -> ChatEngine:
    engine = object.__new__(ChatEngine)
    engine._cancelled = False
    return engine


def test_stream_one_reply_accumulates_and_emits_deltas(monkeypatch) -> None:
    def fake_chat_completion(client, provider_id=None, **kwargs):
        yield _chunk("Hel")
        yield _chunk("lo")

    monkeypatch.setattr(ce, "chat_completion", fake_chat_completion)
    ws = FakeWebSocket()

    text = asyncio.run(
        ChatEngine._stream_one_reply(
            _engine(),
            ws,
            message_id="m1",
            conv_id="c1",
            client=SimpleNamespace(base_url=""),
            model="test-model",
            provider_id="p1",
            provider_family="openai",
            messages=[{"role": "user", "content": "hi"}],
            max_output=1024,
        )
    )

    assert text == "Hello"
    deltas = [m for m in ws.messages if m["type"] == "chat.delta"]
    assert [d["content"] for d in deltas] == ["Hel", "lo"]
    assert deltas[0]["message_id"] == "m1"
    assert deltas[0]["conversation_id"] == "c1"


def test_stream_one_reply_carries_speaker_identity(monkeypatch) -> None:
    def fake_chat_completion(client, provider_id=None, **kwargs):
        yield _chunk("hi")

    monkeypatch.setattr(ce, "chat_completion", fake_chat_completion)
    ws = FakeWebSocket()

    asyncio.run(
        ChatEngine._stream_one_reply(
            _engine(),
            ws,
            message_id="m1",
            conv_id="c1",
            client=SimpleNamespace(base_url=""),
            model="test-model",
            provider_id="p1",
            provider_family="openai",
            messages=[],
            max_output=1024,
            character=SimpleNamespace(id=7),
            char_name="Mira",
        )
    )

    delta = next(m for m in ws.messages if m["type"] == "chat.delta")
    assert delta["character_id"] == 7
    assert delta["character_name"] == "Mira"


def test_stream_one_reply_stops_on_should_stop(monkeypatch) -> None:
    stop = {"flag": False}

    def fake_chat_completion(client, provider_id=None, **kwargs):
        yield _chunk("first")
        stop["flag"] = True
        yield _chunk("second")

    monkeypatch.setattr(ce, "chat_completion", fake_chat_completion)
    ws = FakeWebSocket()

    text = asyncio.run(
        ChatEngine._stream_one_reply(
            _engine(),
            ws,
            message_id="m1",
            conv_id="c1",
            client=SimpleNamespace(base_url=""),
            model="test-model",
            provider_id="p1",
            provider_family="openai",
            messages=[],
            max_output=1024,
            should_stop=lambda: stop["flag"],
        )
    )

    assert text == "first"


def test_stream_one_reply_stops_on_engine_cancel_by_default(monkeypatch) -> None:
    def fake_chat_completion(client, provider_id=None, **kwargs):
        yield _chunk("first")
        engine._cancelled = True
        yield _chunk("second")

    monkeypatch.setattr(ce, "chat_completion", fake_chat_completion)
    engine = _engine()
    ws = FakeWebSocket()

    text = asyncio.run(
        ChatEngine._stream_one_reply(
            engine,
            ws,
            message_id="m1",
            conv_id="c1",
            client=SimpleNamespace(base_url=""),
            model="test-model",
            provider_id="p1",
            provider_family="openai",
            messages=[],
            max_output=1024,
        )
    )

    assert text == "first"


def test_stream_one_reply_reports_llm_failure_as_text(monkeypatch) -> None:
    def fake_chat_completion(client, provider_id=None, **kwargs):
        raise RuntimeError("boom")
        yield

    monkeypatch.setattr(ce, "chat_completion", fake_chat_completion)
    ws = FakeWebSocket()

    text = asyncio.run(
        ChatEngine._stream_one_reply(
            _engine(),
            ws,
            message_id="m1",
            conv_id="c1",
            client=SimpleNamespace(base_url=""),
            model="test-model",
            provider_id="p1",
            provider_family="openai",
            messages=[],
            max_output=1024,
        )
    )

    assert "LLM call failed" in text
    assert "boom" in text

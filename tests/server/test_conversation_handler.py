# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from src.server.handlers import conversation


class _WebSocket:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send_json(self, message: dict) -> None:
        self.messages.append(message)


def test_history_returns_messages_with_session_character(monkeypatch):
    stored_message = SimpleNamespace(to_dict=lambda: {
        "id": 1,
        "session_id": "session-1",
        "role": "assistant",
        "content": "hello",
    })
    store = SimpleNamespace(
        get_session_messages=lambda conversation_id, limit: [stored_message],
        get_character=lambda conversation_id: 7,
    )
    card_repo = SimpleNamespace(
        get_character=lambda character_id: SimpleNamespace(name="Ava"),
    )
    monkeypatch.setattr(
        conversation,
        "_engine",
        SimpleNamespace(session_store=store, card_repo=card_repo),
    )
    ws = _WebSocket()

    handled = asyncio.run(conversation.dispatch(ws, {
        "type": "conversation.history",
        "conversation_id": "session-1",
    }))

    assert handled is True
    assert ws.messages == [{
        "type": "conversation.history",
        "conversation_id": "session-1",
        "messages": [{
            "id": 1,
            "session_id": "session-1",
            "role": "assistant",
            "content": "hello",
            "character_id": 7,
            "character_name": "Ava",
        }],
    }]

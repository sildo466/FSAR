from __future__ import annotations

import asyncio
from collections import deque
from types import SimpleNamespace

from src.server.chat_engine import ChatEngine


class FakeWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send_json(self, message: dict) -> None:
        self.messages.append(message)


class FakeSessionStore:
    def __init__(self) -> None:
        self.character_id: int | None = None

    def get(self, conversation_id: str):
        return SimpleNamespace(id=conversation_id)

    def get_character(self, conversation_id: str) -> int | None:
        return self.character_id

    def set_character(self, conversation_id: str, character_id: int) -> None:
        self.character_id = character_id


def test_send_binds_requested_character_before_thinking_event() -> None:
    character = SimpleNamespace(id=7, name="Coding Coach")
    engine = object.__new__(ChatEngine)
    engine.session_store = FakeSessionStore()
    engine.card_repo = SimpleNamespace(
        get_character=lambda character_id: character if character_id == 7 else None,
        get_default_character=lambda: SimpleNamespace(id=1, name="FSAR"),
    )
    engine._active_conv_id = None
    engine._cancelled = False
    engine._conv_locks = {}
    engine.client_and_model = lambda: (None, "", "")

    async def done(ws, message_id, outcome, conv_id=None):
        await ws.send_json({"type": "chat.done", "message_id": message_id, "outcome": outcome})

    engine._done = done
    websocket = FakeWebSocket()

    asyncio.run(
        ChatEngine.handle_send(
            engine,
            websocket,
            "hello",
            "agent",
            "session-1",
            character_id=7,
        )
    )

    assert engine.session_store.character_id == 7
    thinking = next(message for message in websocket.messages if message["type"] == "chat.thinking")
    assert thinking["character_id"] == 7
    assert thinking["character_name"] == "Coding Coach"


def test_send_binds_character_before_conversation_created_event() -> None:
    character = SimpleNamespace(id=7, name="Coding Coach")

    class CreatingStore:
        def __init__(self) -> None:
            self.character_id: int | None = None

        def create(self):
            return SimpleNamespace(id="new-1", to_dict=lambda: {"id": "new-1"})

        def get(self, conversation_id: str):
            return SimpleNamespace(id=conversation_id)

        def get_character(self, conversation_id: str) -> int | None:
            return self.character_id

        def set_character(self, conversation_id: str, character_id: int) -> None:
            self.character_id = character_id

    store = CreatingStore()

    class OrderTrackingWebSocket(FakeWebSocket):
        def __init__(self) -> None:
            super().__init__()
            self.character_at_created: int | None | str = "UNSET"

        async def send_json(self, message: dict) -> None:
            await super().send_json(message)
            if message.get("type") == "conversation.created":
                self.character_at_created = store.character_id

    engine = object.__new__(ChatEngine)
    engine.session_store = store
    engine.workspace_repo = SimpleNamespace(get_or_create_binding=lambda conv_id: None)
    engine.card_repo = SimpleNamespace(
        get_character=lambda character_id: character if character_id == 7 else None,
        get_default_character=lambda: SimpleNamespace(id=1, name="FSAR"),
    )
    engine._active_conv_id = None
    engine._cancelled = False
    engine._conv_locks = {}
    engine.client_and_model = lambda: (None, "", "")

    async def done(ws, message_id, outcome, conv_id=None):
        await ws.send_json({"type": "chat.done", "message_id": message_id, "outcome": outcome})

    engine._done = done
    websocket = OrderTrackingWebSocket()

    asyncio.run(
        ChatEngine.handle_send(
            engine,
            websocket,
            "hello",
            "agent",
            None,
            character_id=7,
            selected_chat_model={"kind": "model", "id": "m"},
        )
    )

    created = next(message for message in websocket.messages if message["type"] == "conversation.created")
    assert created["session"]["id"] == "new-1"
    assert websocket.character_at_created == 7


def test_regenerate_replays_last_user_prompt_without_saving_it_again() -> None:
    rows = [
        SimpleNamespace(id=1, role="user", content="Hello"),
        SimpleNamespace(id=2, role="assistant", content="Old reply"),
        SimpleNamespace(id=3, role="assistant", content="Older extra"),
    ]

    class RegenerateStore:
        def __init__(self) -> None:
            self.character_id: int | None = None
            self.deleted: list[int] | None = None

        def get(self, conversation_id: str):
            return SimpleNamespace(id=conversation_id)

        def get_character(self, conversation_id: str) -> int | None:
            return self.character_id

        def set_character(self, conversation_id: str, character_id: int) -> None:
            self.character_id = character_id

        def get_session_messages(self, conversation_id: str):
            return list(rows)

        def delete_messages(self, message_ids: list[int]) -> int:
            self.deleted = list(message_ids)
            return len(message_ids)

    store = RegenerateStore()
    engine = object.__new__(ChatEngine)
    engine.session_store = store
    engine.card_repo = SimpleNamespace(
        get_character=lambda character_id: None,
        get_default_character=lambda: SimpleNamespace(id=1, name="FSAR"),
    )
    engine._active_conv_id = None
    engine._cancelled = False
    engine._conv_locks = {}
    engine._short_cache = {
        "session-1": deque([
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Old reply"},
        ]),
    }
    engine._ensure_short = lambda conv_id: None

    captured: dict = {}

    async def fake_run_reply(ws, content, mode, conv_id, character, char_name,
                             selected_chat_model=None, save_user=True):
        captured.update(
            content=content, conv_id=conv_id, character=character,
            char_name=char_name, save_user=save_user,
        )

    engine._run_reply = fake_run_reply
    websocket = FakeWebSocket()

    asyncio.run(
        ChatEngine.handle_regenerate(
            engine, websocket, "agent", "session-1",
        )
    )

    assert store.deleted == [2, 3]
    assert store.character_id == 1
    assert captured["content"] == "Hello"
    assert captured["conv_id"] == "session-1"
    assert captured["save_user"] is False
    assert engine._short_cache["session-1"][-1]["role"] == "user"


def test_regenerate_without_user_message_reports_no_prompt() -> None:
    class EmptyStore:
        def get(self, conversation_id: str):
            return SimpleNamespace(id=conversation_id)

        def get_session_messages(self, conversation_id: str):
            return []

    engine = object.__new__(ChatEngine)
    engine.session_store = EmptyStore()
    engine._active_conv_id = None
    websocket = FakeWebSocket()

    asyncio.run(
        ChatEngine.handle_regenerate(engine, websocket, "agent", "session-1")
    )

    error = next(message for message in websocket.messages if message["type"] == "error")
    assert error["code"] == "no_prompt"

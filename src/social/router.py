"""Route inbound social events into FSAR and queue outbound replies."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from src.server.chat_engine import handle_user_agent_message
from src.social.channels import ChannelAdapter, ChannelEvent, ReplyTarget
from src.social.outbox import Outbox
from src.social.state import (
    is_muted,
    load_or_create_session,
    touch_binding,
    upsert_binding,
)


log = logging.getLogger(__name__)


class ChannelRouter:
    def __init__(self) -> None:
        self._adapters: dict[str, ChannelAdapter] = {}
        self._outbox_task: asyncio.Task[None] | None = None
        self.outbox = Outbox(self._get_adapter)

    def register(self, adapter: ChannelAdapter) -> None:
        self._adapters[adapter.name] = adapter

    def _get_adapter(self, platform: str) -> ChannelAdapter | None:
        return self._adapters.get(platform)

    def get(self, platform: str) -> ChannelAdapter | None:
        return self._adapters.get(platform)

    async def outbox_send(self, target: ReplyTarget, text: str) -> None:
        self.outbox.enqueue(target, text)

    async def start_outbox(self) -> None:
        if self._outbox_task is None or self._outbox_task.done():
            self._outbox_task = asyncio.create_task(
                self.outbox.run_forever(),
                name="social-outbox",
            )

    async def stop_outbox(self) -> None:
        self.outbox.stop()
        if self._outbox_task is None:
            return
        self._outbox_task.cancel()
        with suppress(asyncio.CancelledError):
            await self._outbox_task
        self._outbox_task = None

    async def handle(self, event: ChannelEvent) -> None:
        try:
            if is_muted(event.platform, event.peer_id):
                log.info(
                    "social: dropped muted peer %s/%s",
                    event.platform,
                    event.peer_id,
                )
                return

            upsert_binding(event.platform, event.peer_id, display_name=None)
            touch_binding(event.platform, event.peer_id)
            session_id = load_or_create_session(event.platform, event.peer_id)
            reply_text = await handle_user_agent_message(
                session_id,
                event.text,
                character_card_id=event.character_card_id,
                user_card_id=event.user_card_id,
            )
            if reply_text:
                await self.outbox_send(event.reply_target, reply_text)
        except Exception:
            log.exception("social: router handle error for %s", event.platform)

"""Telegram Bot API adapter with text-only long polling."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from telegram import Update
from telegram.error import (
    BadRequest as TelegramBadRequest,
    Forbidden,
    InvalidToken,
    NetworkError,
    RetryAfter,
    TimedOut,
)
from telegram.ext import Application, MessageHandler, filters

from src.social.channels import (
    BadRequest,
    ChannelAdapter,
    ChannelEvent,
    ChannelError,
    PermanentAuth,
    RateLimit,
    ReplyTarget,
    TransientNetwork,
)
from src.social.state import load_cursor, save_cursor


log = logging.getLogger(__name__)


def _retry_seconds(error: RetryAfter) -> float:
    retry_after = error.retry_after
    if hasattr(retry_after, "total_seconds"):
        return float(retry_after.total_seconds())
    return float(retry_after)


def _normalize_error(error: Exception) -> ChannelError:
    if isinstance(error, (InvalidToken, Forbidden)):
        return PermanentAuth(str(error))
    if isinstance(error, RetryAfter):
        return RateLimit(str(error), retry_after=_retry_seconds(error))
    if isinstance(error, (TimedOut, NetworkError)):
        return TransientNetwork(str(error))
    if isinstance(error, TelegramBadRequest):
        return BadRequest(str(error))
    return ChannelError(str(error))


class TelegramAdapter(ChannelAdapter):
    name = "telegram"

    def __init__(self, bot_token: str) -> None:
        self._token = bot_token
        self._app: Application | None = None
        self._poll_task: asyncio.Task[None] | None = None
        self._offset = 0

    async def start(self, router) -> None:
        cursor = load_cursor(self.name)
        self._offset = int(cursor.get("offset", 0))
        self._app = Application.builder().token(self._token).build()
        self._app.add_handler(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                self._make_callback(router),
            )
        )
        try:
            await self._app.initialize()
            await self._app.start()
            await self._app.bot.delete_webhook(drop_pending_updates=False)
        except (InvalidToken, Forbidden, RetryAfter, NetworkError, TelegramBadRequest) as exc:
            raise _normalize_error(exc) from exc
        self._poll_task = asyncio.create_task(
            self._poll_loop(),
            name="social-telegram-poll",
        )

    def _make_callback(self, router):
        async def _on_message(update: Update, _context) -> None:
            message = update.effective_message
            user = update.effective_user
            if message is None or not message.text or (user and user.is_bot):
                return
            event = ChannelEvent(
                platform=self.name,
                peer_id=str(message.chat.id),
                peer_kind="dm" if message.chat.type == "private" else "group",
                message_id=str(message.message_id),
                text=message.text,
                sent_at=message.date,
                reply_target=ReplyTarget(
                    platform=self.name,
                    peer_id=str(message.chat.id),
                    reply_to_message_id=str(message.message_id),
                ),
            )
            await router.handle(event)

        return _on_message

    async def _poll_loop(self) -> None:
        assert self._app is not None
        while self._app.running:
            try:
                updates = await self._app.bot.get_updates(
                    offset=self._offset,
                    timeout=30,
                    allowed_updates=["message"],
                )
                for update in updates:
                    await self._app.process_update(update)
                    self._offset = max(self._offset, update.update_id + 1)
                    save_cursor(self.name, {"offset": self._offset})
            except asyncio.CancelledError:
                raise
            except RetryAfter as exc:
                await asyncio.sleep(_retry_seconds(exc))
            except (TimedOut, NetworkError) as exc:
                log.warning("telegram polling network error: %s", exc)
                await asyncio.sleep(2)
            except (InvalidToken, Forbidden) as exc:
                log.error("telegram polling stopped: %s", exc)
                return
            except Exception:
                log.exception("telegram polling failed")
                await asyncio.sleep(2)

    async def stop(self) -> None:
        if self._poll_task is not None:
            self._poll_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._poll_task
            self._poll_task = None
        if self._app is not None:
            if self._app.running:
                await self._app.stop()
            await self._app.shutdown()
            self._app = None

    async def send(self, target: ReplyTarget, text: str) -> None:
        if self._app is None or not self._app.running:
            raise TransientNetwork("telegram adapter is not running")
        reply_to = (
            int(target.reply_to_message_id)
            if target.reply_to_message_id
            else None
        )
        try:
            await self._app.bot.send_message(
                chat_id=int(target.peer_id),
                text=text,
                reply_to_message_id=reply_to,
            )
        except (InvalidToken, Forbidden, RetryAfter, NetworkError, TelegramBadRequest) as exc:
            raise _normalize_error(exc) from exc

    def status(self) -> dict:
        running = bool(
            self._app
            and self._app.running
            and self._poll_task
            and not self._poll_task.done()
        )
        return {
            "platform": self.name,
            "state": "running" if running else "paused",
        }

"""Feishu Open Platform adapter with verified text-only webhooks."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
    ReplyMessageRequest,
    ReplyMessageRequestBody,
)
from lark_oapi.core.model import RawRequest, RawResponse
from lark_oapi.event.dispatcher_handler import EventDispatcherHandler

from src.social.channels import (
    BadRequest,
    ChannelAdapter,
    ChannelEvent,
    PermanentAuth,
    RateLimit,
    ReplyTarget,
    TransientNetwork,
)


log = logging.getLogger(__name__)

_RATE_LIMIT_CODES = {230020, 99991400}
_AUTH_CODES = {99991663, 99991664, 99991668, 99991671, 99991672}


class FeishuAdapter(ChannelAdapter):
    name = "feishu"

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        verification_token: str,
        encrypt_key: str = "",
    ) -> None:
        self._app_id = app_id
        self._app_secret = app_secret
        self._verification_token = verification_token
        self._encrypt_key = encrypt_key
        self._client: lark.Client | None = None
        self._router = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._handler = (
            EventDispatcherHandler.builder(encrypt_key, verification_token)
            .register_p2_im_message_receive_v1(self._on_message)
            .build()
        )

    async def start(self, router) -> None:
        self._client = (
            lark.Client.builder()
            .app_id(self._app_id)
            .app_secret(self._app_secret)
            .build()
        )
        self._router = router
        self._loop = asyncio.get_running_loop()

    async def stop(self) -> None:
        self._client = None
        self._router = None
        self._loop = None

    def handle_webhook(
        self,
        body: bytes,
        headers: dict[str, str],
        uri: str,
    ) -> RawResponse:
        request = RawRequest()
        request.body = body
        request.headers = headers
        request.uri = uri
        return self._handler.do(request)

    def _on_message(self, data) -> None:
        event = getattr(data, "event", None)
        message = getattr(event, "message", None)
        sender = getattr(event, "sender", None)
        if message is None or sender is None:
            return
        if getattr(sender, "sender_type", "") in {"app", "bot"}:
            return
        if getattr(message, "message_type", "") != "text":
            return

        try:
            content = json.loads(getattr(message, "content", "{}") or "{}")
        except (TypeError, json.JSONDecodeError):
            return
        text = str(content.get("text") or "")
        chat_type = str(getattr(message, "chat_type", "p2p") or "p2p")
        mentions = getattr(message, "mentions", None) or []
        if chat_type != "p2p" and not mentions:
            return
        for mention in mentions:
            key = str(getattr(mention, "key", "") or "")
            if key:
                text = text.replace(key, "")
        text = text.strip()
        if not text:
            return

        chat_id = str(getattr(message, "chat_id", "") or "")
        message_id = str(getattr(message, "message_id", "") or "")
        if not chat_id or not message_id:
            return
        thread_id = str(getattr(message, "thread_id", "") or "") or None
        channel_event = ChannelEvent(
            platform=self.name,
            peer_id=chat_id,
            peer_kind="dm" if chat_type == "p2p" else "group",
            message_id=message_id,
            text=text,
            sent_at=self._sent_at(getattr(message, "create_time", None)),
            reply_target=ReplyTarget(
                platform=self.name,
                peer_id=chat_id,
                reply_to_message_id=message_id,
                thread_id=thread_id,
            ),
        )
        if self._router is None or self._loop is None or self._loop.is_closed():
            return
        future = asyncio.run_coroutine_threadsafe(
            self._router.handle(channel_event),
            self._loop,
        )
        future.add_done_callback(self._log_callback_error)

    @staticmethod
    def _sent_at(value) -> datetime:
        try:
            return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            return datetime.now(timezone.utc)

    @staticmethod
    def _log_callback_error(future) -> None:
        try:
            future.result()
        except Exception:
            log.exception("feishu inbound routing failed")

    async def send(self, target: ReplyTarget, text: str) -> None:
        if self._client is None:
            raise TransientNetwork("feishu adapter is not running")
        content = json.dumps({"text": text}, ensure_ascii=False)
        if target.reply_to_message_id:
            body = (
                ReplyMessageRequestBody.builder()
                .content(content)
                .msg_type("text")
                .reply_in_thread(bool(target.thread_id))
                .uuid(str(uuid.uuid4()))
                .build()
            )
            request = (
                ReplyMessageRequest.builder()
                .message_id(target.reply_to_message_id)
                .request_body(body)
                .build()
            )
            call = self._client.im.v1.message.reply
        else:
            body = (
                CreateMessageRequestBody.builder()
                .receive_id(target.peer_id)
                .msg_type("text")
                .content(content)
                .uuid(str(uuid.uuid4()))
                .build()
            )
            request = (
                CreateMessageRequest.builder()
                .receive_id_type("chat_id")
                .request_body(body)
                .build()
            )
            call = self._client.im.v1.message.create

        try:
            response = await asyncio.to_thread(call, request)
        except Exception as exc:
            raise TransientNetwork(str(exc)) from exc
        if response.success():
            return
        code = int(getattr(response, "code", -1) or -1)
        message = str(getattr(response, "msg", "feishu send failed"))
        if code in _RATE_LIMIT_CODES:
            raise RateLimit(f"[{code}] {message}")
        if code in _AUTH_CODES:
            raise PermanentAuth(f"[{code}] {message}")
        raise BadRequest(f"[{code}] {message}")

    def status(self) -> dict:
        return {
            "platform": self.name,
            "state": "running" if self._client is not None else "paused",
        }

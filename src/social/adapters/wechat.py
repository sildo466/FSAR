"""WeChat text adapter for Tencent's iLink Bot API."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import secrets
import ssl
import uuid
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

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

_ILINK_BASE_URL = "https://ilinkai.weixin.qq.com"
_ILINK_APP_ID = "bot"
_ILINK_CLIENT_VERSION = (2 << 16) | (2 << 8)
_CHANNEL_VERSION = "2.2.0"
_GET_UPDATES = "ilink/bot/getupdates"
_SEND_MESSAGE = "ilink/bot/sendmessage"
_GET_BOT_QR = "ilink/bot/get_bot_qrcode"
_GET_QR_STATUS = "ilink/bot/get_qrcode_status"
_TOKEN_PATH = Path("data/social_accounts/wechat.json")

_ITEM_TEXT = 1
_MESSAGE_TYPE_BOT = 2
_MESSAGE_STATE_FINISH = 2
_SESSION_EXPIRED = -14
_RATE_LIMITED = -2


class _AccountStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._data = self._load()

    def _load(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        try:
            value = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(self._data, ensure_ascii=False),
            encoding="utf-8",
        )
        temporary.replace(self._path)

    def credentials(self) -> dict[str, str]:
        return {
            "account_id": str(self._data.get("account_id") or ""),
            "bot_token": str(self._data.get("bot_token") or ""),
            "base_url": str(self._data.get("base_url") or ""),
            "user_id": str(self._data.get("user_id") or ""),
        }

    def set_credentials(self, credentials: dict[str, str]) -> None:
        self._data.update(credentials)
        self.save()

    def sync_buf(self) -> str:
        return str(self._data.get("get_updates_buf") or "")

    def set_sync_buf(self, value: str) -> None:
        self._data["get_updates_buf"] = value
        self.save()

    def context_token(self, peer_id: str) -> str | None:
        tokens = self._data.get("context_tokens") or {}
        if not isinstance(tokens, dict):
            return None
        value = str(tokens.get(peer_id) or "")
        return value or None

    def set_context_token(self, peer_id: str, token: str) -> None:
        tokens = self._data.setdefault("context_tokens", {})
        if not isinstance(tokens, dict):
            tokens = {}
            self._data["context_tokens"] = tokens
        tokens[peer_id] = token
        self.save()

    def clear_context_token(self, peer_id: str) -> None:
        tokens = self._data.get("context_tokens")
        if isinstance(tokens, dict) and tokens.pop(peer_id, None) is not None:
            self.save()

    def clear_account_state(self) -> None:
        """Drop cursors and per-peer context that belong to the previous account."""
        self._data.pop("get_updates_buf", None)
        self._data.pop("context_tokens", None)
        self.save()


def _wechat_uin() -> str:
    value = int.from_bytes(secrets.token_bytes(4), "big")
    return base64.b64encode(str(value).encode()).decode()


def _extract_text(message: dict[str, Any]) -> str:
    for item in message.get("item_list") or []:
        if item.get("type") == _ITEM_TEXT:
            return str((item.get("text_item") or {}).get("text") or "").strip()
    return ""


class WeChatAdapter(ChannelAdapter):
    name = "wechat"

    def __init__(
        self,
        account_id: str = "",
        bot_token: str = "",
        base_url: str = "",
        character_card_id: int | None = None,
        user_card_id: int | None = None,
    ) -> None:
        self._character_card_id = (
            int(character_card_id) if character_card_id is not None else None
        )
        self._user_card_id = (
            int(user_card_id) if user_card_id is not None else None
        )
        self._store = _AccountStore(_TOKEN_PATH)
        stored = self._store.credentials()
        self._account_id = account_id or stored["account_id"]
        self._token = bot_token or stored["bot_token"]
        self._base_url = (
            base_url or stored["base_url"] or _ILINK_BASE_URL
        ).rstrip("/")
        self._user_id = stored["user_id"]
        self._router = None
        self._client: httpx.AsyncClient | None = None
        self._poll_task: asyncio.Task[None] | None = None
        self._qr_code = ""
        self._qr_base_url = _ILINK_BASE_URL
        self._replacing = False
        self._seen_message_ids: set[str] = set()
        if self._account_id and self._token:
            self._store.set_credentials(
                {
                    "account_id": self._account_id,
                    "bot_token": self._token,
                    "base_url": self._base_url,
                    "user_id": self._user_id,
                }
            )

    async def start(self, router) -> None:
        self._router = router
        self._ensure_client()
        self._start_polling_if_ready()

    async def _stop_polling(self) -> None:
        if self._poll_task is not None:
            self._poll_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._poll_task
            self._poll_task = None

    async def stop(self) -> None:
        await self._stop_polling()
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        self._router = None

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            # httpx defaults to the certifi bundle, which omits locally installed
            # authorities, so a TLS-terminating proxy fails every iLink call.
            self._client = httpx.AsyncClient(
                timeout=None,
                verify=ssl.create_default_context(),
            )
        return self._client

    def _start_polling_if_ready(self) -> None:
        if not self._account_id or not self._token or self._router is None:
            return
        if self._poll_task is None or self._poll_task.done():
            self._poll_task = asyncio.create_task(
                self._poll_loop(),
                name="social-wechat-poll",
            )

    async def begin_qr_login(self) -> dict[str, str]:
        response = await self._api_get(
            _ILINK_BASE_URL,
            f"{_GET_BOT_QR}?bot_type=3",
        )
        self._qr_code = str(response.get("qrcode") or "")
        scan_data = str(response.get("qrcode_img_content") or self._qr_code)
        if not self._qr_code or not scan_data:
            raise BadRequest("iLink QR response was incomplete")
        self._qr_base_url = _ILINK_BASE_URL
        self._replacing = False
        return {"qrcode": self._qr_code, "scan_data": scan_data}

    async def reset_qr_login(self) -> dict[str, str]:
        """Start a replacement QR login, leaving the live session untouched.

        Credentials are only overwritten once iLink confirms the new scan, so an
        expired or abandoned QR leaves the current account still polling.
        """
        result = await self.begin_qr_login()
        self._replacing = True
        return result

    async def check_qr_login(self) -> dict[str, str]:
        if not self._qr_code:
            raise BadRequest("no iLink QR login is pending")
        response = await self._api_get(
            self._qr_base_url,
            f"{_GET_QR_STATUS}?qrcode={self._qr_code}",
        )
        status = str(response.get("status") or "wait")
        if status == "scaned_but_redirect":
            redirect_host = str(response.get("redirect_host") or "")
            if redirect_host:
                self._qr_base_url = f"https://{redirect_host}"
        if status != "confirmed":
            return {"status": status}

        account_id = str(response.get("ilink_bot_id") or "")
        token = str(response.get("bot_token") or "")
        if not account_id or not token:
            raise PermanentAuth("iLink confirmed QR without credentials")
        switching = self._replacing and account_id != self._account_id
        if switching:
            await self._stop_polling()
            self._store.clear_account_state()
        self._replacing = False
        self._account_id = account_id
        self._token = token
        self._base_url = str(response.get("baseurl") or _ILINK_BASE_URL).rstrip("/")
        self._user_id = str(response.get("ilink_user_id") or "")
        self._store.set_credentials(
            {
                "account_id": self._account_id,
                "bot_token": self._token,
                "base_url": self._base_url,
                "user_id": self._user_id,
            }
        )
        self._qr_code = ""
        self._start_polling_if_ready()
        return {"status": "confirmed", "account_id": self._account_id}

    async def _api_get(self, base_url: str, endpoint: str) -> dict[str, Any]:
        client = self._ensure_client()
        headers = {
            "iLink-App-Id": _ILINK_APP_ID,
            "iLink-App-ClientVersion": str(_ILINK_CLIENT_VERSION),
        }
        try:
            response = await asyncio.wait_for(
                client.get(f"{base_url.rstrip('/')}/{endpoint}", headers=headers),
                timeout=35,
            )
        except (httpx.RequestError, asyncio.TimeoutError) as exc:
            raise TransientNetwork(str(exc)) from exc
        return self._response_json(response)

    async def _api_post(
        self,
        endpoint: str,
        payload: dict[str, Any],
        *,
        timeout: float,
    ) -> dict[str, Any]:
        client = self._ensure_client()
        body = json.dumps(
            {**payload, "base_info": {"channel_version": _CHANNEL_VERSION}},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        headers = {
            "Content-Type": "application/json",
            "AuthorizationType": "ilink_bot_token",
            "Content-Length": str(len(body.encode("utf-8"))),
            "X-WECHAT-UIN": _wechat_uin(),
            "iLink-App-Id": _ILINK_APP_ID,
            "iLink-App-ClientVersion": str(_ILINK_CLIENT_VERSION),
            "Authorization": f"Bearer {self._token}",
        }
        try:
            response = await asyncio.wait_for(
                client.post(
                    f"{self._base_url}/{endpoint}",
                    content=body,
                    headers=headers,
                ),
                timeout=timeout,
            )
        except asyncio.TimeoutError as exc:
            raise TransientNetwork("iLink request timed out") from exc
        except httpx.RequestError as exc:
            raise TransientNetwork(str(exc)) from exc
        return self._response_json(response)

    @staticmethod
    def _response_json(response: httpx.Response) -> dict[str, Any]:
        if response.status_code in {401, 403}:
            raise PermanentAuth(f"iLink HTTP {response.status_code}")
        if response.status_code == 429:
            raise RateLimit("iLink HTTP 429", retry_after=30)
        if response.status_code >= 500:
            raise TransientNetwork(f"iLink HTTP {response.status_code}")
        if response.status_code >= 400:
            raise BadRequest(f"iLink HTTP {response.status_code}: {response.text[:200]}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise TransientNetwork("iLink returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise TransientNetwork("iLink returned a non-object response")
        return payload

    async def _poll_loop(self) -> None:
        sync_buf = self._store.sync_buf()
        timeout_ms = 35_000
        while True:
            try:
                response = await self._api_post(
                    _GET_UPDATES,
                    {"get_updates_buf": sync_buf},
                    timeout=(timeout_ms / 1000) + 5,
                )
                timeout_value = response.get("longpolling_timeout_ms")
                if isinstance(timeout_value, int) and timeout_value > 0:
                    timeout_ms = timeout_value
                ret = response.get("ret", 0)
                error_code = response.get("errcode", 0)
                if ret not in {0, None} or error_code not in {0, None}:
                    if ret == _SESSION_EXPIRED or error_code == _SESSION_EXPIRED:
                        raise PermanentAuth("iLink session expired")
                    if ret == _RATE_LIMITED or error_code == _RATE_LIMITED:
                        raise RateLimit("iLink getupdates rate limited", retry_after=30)
                    raise BadRequest(
                        str(response.get("errmsg") or "iLink getupdates failed")
                    )

                for message in response.get("msgs") or []:
                    if isinstance(message, dict):
                        await self._process_message(message)
                new_sync_buf = str(response.get("get_updates_buf") or "")
                if new_sync_buf:
                    sync_buf = new_sync_buf
                    self._store.set_sync_buf(sync_buf)
            except asyncio.CancelledError:
                raise
            except PermanentAuth as exc:
                log.error("wechat polling stopped: %s", exc)
                return
            except RateLimit as exc:
                await asyncio.sleep(exc.retry_after or 30)
            except (TransientNetwork, BadRequest) as exc:
                log.warning("wechat polling error: %s", exc)
                await asyncio.sleep(2)

    async def _process_message(self, message: dict[str, Any]) -> None:
        sender_id = str(message.get("from_user_id") or "")
        if not sender_id or sender_id == self._account_id:
            return
        message_id = str(message.get("message_id") or "")
        if message_id and message_id in self._seen_message_ids:
            return
        if message_id:
            self._seen_message_ids.add(message_id)
            if len(self._seen_message_ids) > 1000:
                self._seen_message_ids.pop()
        text = _extract_text(message)
        if not text:
            return

        room_id = str(
            message.get("room_id") or message.get("chat_room_id") or ""
        )
        peer_id = room_id or sender_id
        context_token = str(message.get("context_token") or "")
        if context_token:
            self._store.set_context_token(peer_id, context_token)
        if self._router is None:
            return
        await self._router.handle(
            ChannelEvent(
                platform=self.name,
                peer_id=peer_id,
                peer_kind="group" if room_id else "dm",
                message_id=message_id or uuid.uuid4().hex,
                text=text,
                sent_at=datetime.now(timezone.utc),
                reply_target=ReplyTarget(
                    platform=self.name,
                    peer_id=peer_id,
                    reply_to_message_id=message_id or None,
                ),
                character_card_id=self._character_card_id,
                user_card_id=self._user_card_id,
            )
        )

    def default_peer(self) -> str | None:
        return self._user_id or None

    async def send(self, target: ReplyTarget, text: str) -> None:
        if not self._token or self._client is None:
            raise PermanentAuth("wechat QR login is required")
        context_token = self._store.context_token(target.peer_id)
        response = await self._send_text(target.peer_id, text, context_token)
        ret = response.get("ret", 0)
        error_code = response.get("errcode", 0)
        if (
            (ret == _SESSION_EXPIRED or error_code == _SESSION_EXPIRED)
            and context_token
        ):
            self._store.clear_context_token(target.peer_id)
            response = await self._send_text(target.peer_id, text, None)
            ret = response.get("ret", 0)
            error_code = response.get("errcode", 0)
        if ret in {0, None} and error_code in {0, None}:
            return
        message = str(response.get("errmsg") or "iLink sendmessage failed")
        if ret == _RATE_LIMITED or error_code == _RATE_LIMITED:
            raise RateLimit(message, retry_after=30)
        if ret == _SESSION_EXPIRED or error_code == _SESSION_EXPIRED:
            raise PermanentAuth(message)
        raise BadRequest(message)

    async def _send_text(
        self,
        peer_id: str,
        text: str,
        context_token: str | None,
    ) -> dict[str, Any]:
        message: dict[str, Any] = {
            "from_user_id": "",
            "to_user_id": peer_id,
            "client_id": f"fsar-wechat-{uuid.uuid4().hex}",
            "message_type": _MESSAGE_TYPE_BOT,
            "message_state": _MESSAGE_STATE_FINISH,
            "item_list": [
                {"type": _ITEM_TEXT, "text_item": {"text": text}}
            ],
        }
        if context_token:
            message["context_token"] = context_token
        return await self._api_post(
            _SEND_MESSAGE,
            {"msg": message},
            timeout=15,
        )

    def status(self) -> dict:
        running = bool(self._poll_task and not self._poll_task.done())
        return {
            "platform": self.name,
            "state": "running" if running else "paused",
            "login_required": not bool(self._account_id and self._token),
            "account_id": self._account_id,
        }

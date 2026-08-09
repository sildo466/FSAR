"""Build and manage social adapters for the FastAPI server lifecycle."""

from __future__ import annotations

import logging

from src.social.adapters.feishu import FeishuAdapter
from src.social.adapters.telegram import TelegramAdapter
from src.social.adapters.wechat import WeChatAdapter
from src.social.channels import ChannelAdapter
from src.social.router import ChannelRouter
from src.utils.fsar_config import get_default_config


log = logging.getLogger(__name__)


def _load_config() -> dict:
    value = get_default_config().get("social", {}) or {}
    return value if isinstance(value, dict) else {}


def _coerce_int(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


_current_router: ChannelRouter | None = None


def set_current_router(router: ChannelRouter | None) -> None:
    """Publish the live router so non-request consumers (scheduler delivery)
    can resolve it lazily — they are constructed before social startup runs."""
    global _current_router
    _current_router = router


def get_current_router() -> ChannelRouter | None:
    return _current_router


def build_router_and_adapters() -> tuple[ChannelRouter, list[ChannelAdapter]]:
    config = _load_config()
    router = ChannelRouter()
    adapters: list[ChannelAdapter] = []

    telegram = config.get("telegram") or {}
    if telegram.get("enabled") and telegram.get("bot_token"):
        adapters.append(TelegramAdapter(str(telegram["bot_token"])))

    feishu = config.get("feishu") or {}
    if (
        feishu.get("enabled")
        and feishu.get("app_id")
        and feishu.get("app_secret")
        and feishu.get("verification_token")
    ):
        adapters.append(
            FeishuAdapter(
                app_id=str(feishu["app_id"]),
                app_secret=str(feishu["app_secret"]),
                verification_token=str(feishu["verification_token"]),
                encrypt_key=str(feishu.get("encrypt_key") or ""),
            )
        )

    wechat = config.get("wechat") or {}
    if wechat.get("enabled"):
        adapters.append(
            WeChatAdapter(
                account_id=str(wechat.get("account_id") or ""),
                bot_token=str(wechat.get("bot_token") or ""),
                base_url=str(wechat.get("base_url") or ""),
                character_card_id=_coerce_int(wechat.get("character_card_id")),
                user_card_id=_coerce_int(wechat.get("user_card_id")),
            )
        )

    for adapter in adapters:
        router.register(adapter)
    return router, adapters


async def start_social(
    router: ChannelRouter,
    adapters: list[ChannelAdapter],
) -> None:
    await router.start_outbox()
    for adapter in adapters:
        try:
            await adapter.start(router)
            log.info("social: %s adapter started", adapter.name)
        except Exception:
            log.exception("social: %s adapter failed to start", adapter.name)


async def stop_social(
    router: ChannelRouter,
    adapters: list[ChannelAdapter],
) -> None:
    for adapter in reversed(adapters):
        try:
            await adapter.stop()
        except Exception:
            log.exception("social: %s adapter failed to stop", adapter.name)
    await router.stop_outbox()

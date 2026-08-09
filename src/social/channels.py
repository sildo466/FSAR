"""Shared channel adapter types for the social bridge."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


PlatformName = Literal["telegram", "feishu", "wechat"]
PeerKind = Literal["dm", "group"]


@dataclass(frozen=True)
class ReplyTarget:
    platform: str
    peer_id: str
    reply_to_message_id: str | None = None
    thread_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChannelEvent:
    platform: PlatformName
    peer_id: str
    peer_kind: PeerKind
    message_id: str
    text: str
    sent_at: datetime
    reply_target: ReplyTarget
    character_card_id: int | None = None
    user_card_id: int | None = None


class ChannelError(Exception):
    """Base normalized error across channel adapters."""

    def __init__(
        self,
        message: str = "",
        *,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class PermanentAuth(ChannelError):
    """Authentication or access failure that cannot be retried."""


class RateLimit(ChannelError):
    """Platform rate limit that may include a retry delay."""


class TransientNetwork(ChannelError):
    """Transient network, timeout, or server failure."""


class BadRequest(ChannelError):
    """Invalid outbound request that cannot be retried."""


class ChannelAdapter(ABC):
    name: PlatformName

    @abstractmethod
    async def start(self, router: "ChannelRouter") -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    async def send(self, target: ReplyTarget, text: str) -> None: ...

    def status(self) -> dict[str, Any]:
        return {"platform": self.name, "state": "unknown"}

    def default_peer(self) -> str | None:
        """Peer id for the bot owner's default conversation, if determinable."""
        return None

from datetime import datetime, timezone

from src.social.channels import (
    ChannelError,
    ChannelEvent,
    PermanentAuth,
    RateLimit,
    ReplyTarget,
)


def test_channel_event_round_trip_through_dataclass():
    target = ReplyTarget(
        platform="telegram",
        peer_id="42",
        reply_to_message_id="100",
    )
    event = ChannelEvent(
        platform="telegram",
        peer_id="42",
        peer_kind="dm",
        message_id="100",
        text="hello",
        sent_at=datetime(2026, 7, 17, tzinfo=timezone.utc),
        reply_target=target,
    )

    assert event.reply_target.peer_id == "42"
    assert event.platform == "telegram"


def test_channel_error_taxonomy():
    rate_limit = RateLimit("rate", retry_after=5)
    assert isinstance(rate_limit, ChannelError)
    assert rate_limit.retry_after == 5
    assert isinstance(PermanentAuth("token gone"), ChannelError)

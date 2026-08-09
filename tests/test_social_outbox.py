import asyncio

import pytest

from src.social.channels import PermanentAuth, RateLimit, ReplyTarget
from src.social.outbox import Outbox


class _FakeAdapter:
    def __init__(self):
        self.name = "telegram"
        self.calls = []
        self.next_error = None

    async def send(self, target, text):
        self.calls.append((target.peer_id, text))
        if self.next_error:
            error, self.next_error = self.next_error, None
            raise error


@pytest.fixture
def journal(tmp_path, monkeypatch):
    path = tmp_path / "queue.jsonl"
    monkeypatch.setattr("src.social.outbox._JOURNAL_PATH", path)
    return path


@pytest.mark.asyncio
async def test_outbox_drains_on_success(journal):
    adapter = _FakeAdapter()
    outbox = Outbox(lambda platform: adapter)
    outbox.enqueue(ReplyTarget(platform="telegram", peer_id="42"), "hi")
    task = asyncio.create_task(outbox.run_forever())
    await asyncio.sleep(0.1)
    outbox.stop()
    await task
    assert adapter.calls == [("42", "hi")]
    assert journal.read_text(encoding="utf-8") == ""


@pytest.mark.asyncio
async def test_outbox_retries_on_rate_limit_then_succeeds(journal):
    adapter = _FakeAdapter()
    adapter.next_error = RateLimit("slow", retry_after=0.05)
    outbox = Outbox(lambda platform: adapter)
    outbox.enqueue(ReplyTarget(platform="telegram", peer_id="42"), "hi")
    task = asyncio.create_task(outbox.run_forever())
    await asyncio.sleep(0.2)
    outbox.stop()
    await task
    assert adapter.calls == [("42", "hi"), ("42", "hi")]


@pytest.mark.asyncio
async def test_outbox_drops_permanent_auth(journal):
    adapter = _FakeAdapter()
    adapter.next_error = PermanentAuth("token gone")
    outbox = Outbox(lambda platform: adapter)
    outbox.enqueue(ReplyTarget(platform="telegram", peer_id="42"), "hi")
    task = asyncio.create_task(outbox.run_forever())
    await asyncio.sleep(0.1)
    outbox.stop()
    await task
    assert adapter.calls == [("42", "hi")]
    assert journal.read_text(encoding="utf-8") == ""


def test_outbox_restores_persisted_messages(journal):
    target = ReplyTarget(platform="telegram", peer_id="42")
    first = Outbox(lambda platform: None)
    first.enqueue(target, "hi")

    restored = Outbox(lambda platform: None)

    assert restored._queue.qsize() == 1

"""Persistent outbound retry queue for social channel replies."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from src.social.channels import (
    BadRequest,
    ChannelAdapter,
    PermanentAuth,
    RateLimit,
    ReplyTarget,
    TransientNetwork,
)


_BASE_BACKOFF = 1.0
_MAX_BACKOFF = 60.0
_JOURNAL_PATH = Path("data/social_outbox/queue.jsonl")


@dataclass
class _Pending:
    target: ReplyTarget
    text: str
    attempts: int = 0
    next_at: float = 0.0


class Outbox:
    def __init__(
        self,
        get_adapter: Callable[[str], ChannelAdapter | None],
    ) -> None:
        self._queue: asyncio.Queue[_Pending] = asyncio.Queue()
        self._pending: list[_Pending] = []
        self._get_adapter = get_adapter
        self._stopped = asyncio.Event()
        self._restore()

    def enqueue(self, target: ReplyTarget, text: str) -> None:
        item = _Pending(target=target, text=text)
        self._pending.append(item)
        self._queue.put_nowait(item)
        self.persist()

    def stop(self) -> None:
        self._stopped.set()
        self.persist()

    def persist(self) -> None:
        _JOURNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = _JOURNAL_PATH.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as stream:
            for item in self._pending:
                payload = {
                    "target": asdict(item.target),
                    "text": item.text,
                    "attempts": item.attempts,
                    "next_at": item.next_at,
                }
                stream.write(json.dumps(payload, ensure_ascii=False) + "\n")
        temporary.replace(_JOURNAL_PATH)

    def _restore(self) -> None:
        if not _JOURNAL_PATH.exists():
            return
        for line in _JOURNAL_PATH.read_text(encoding="utf-8").splitlines():
            try:
                payload = json.loads(line)
                item = _Pending(
                    target=ReplyTarget(**payload["target"]),
                    text=str(payload["text"]),
                    attempts=int(payload.get("attempts", 0)),
                    next_at=float(payload.get("next_at", 0.0)),
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
            self._pending.append(item)
            self._queue.put_nowait(item)

    @staticmethod
    def _backoff(attempts: int) -> float:
        return min(_BASE_BACKOFF * (2**attempts), _MAX_BACKOFF)

    def _complete(self, item: _Pending) -> None:
        try:
            self._pending.remove(item)
        except ValueError:
            pass
        self.persist()

    async def _process(self, item: _Pending) -> None:
        adapter = self._get_adapter(item.target.platform)
        if adapter is None:
            item.next_at = time.time() + self._backoff(item.attempts)
            item.attempts += 1
            self._queue.put_nowait(item)
            self.persist()
            return
        try:
            await adapter.send(item.target, item.text)
        except (PermanentAuth, BadRequest):
            self._complete(item)
        except RateLimit as exc:
            delay = exc.retry_after or self._backoff(item.attempts)
            item.attempts += 1
            item.next_at = time.time() + delay
            self._queue.put_nowait(item)
            self.persist()
        except TransientNetwork:
            delay = self._backoff(item.attempts)
            item.attempts += 1
            item.next_at = time.time() + delay
            self._queue.put_nowait(item)
            self.persist()
        else:
            self._complete(item)

    async def run_forever(self) -> None:
        while not self._stopped.is_set():
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            try:
                wait = max(0.0, item.next_at - time.time())
                if wait:
                    try:
                        await asyncio.wait_for(self._stopped.wait(), timeout=wait)
                    except asyncio.TimeoutError:
                        pass
                    if self._stopped.is_set():
                        return
                await self._process(item)
            finally:
                self._queue.task_done()

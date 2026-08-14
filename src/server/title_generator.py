"""Generate short conversation titles from the first user message."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime
from typing import Any, Callable, Awaitable

from src.utils.fsar_config import FsarConfig
from src.utils.llm_factory import chat_completion
from src.utils.logger import logger
from src.memory.session_store import SessionStore

TITLE_SYSTEM = (
    "Generate a short conversation title.\n"
    "Output ONLY the title text — no thinking, no preamble, no markdown, "
    "no quotation marks, no 'Title:' prefix.\n"
    "Rules:\n"
    "- 6 to 10 characters total (CJK counts as 1 char each).\n"
    "- Capture the user's core intent, not the literal wording.\n"
    "- If the input is unclear, output the most likely topic in <=10 chars."
)

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_ANSWER_RE = re.compile(r"<answer>(.*?)</answer>", re.DOTALL | re.IGNORECASE)


def _strip_think(raw: str) -> str:
    if not raw:
        return ""
    cleaned = _THINK_RE.sub("", raw)
    m = _ANSWER_RE.search(cleaned)
    if m:
        cleaned = m.group(1)
    return cleaned.strip()


class TitleGenerator:
    """Background, fire-and-forget title summarizer.

    Triggered AFTER the assistant finishes its first reply. On failure,
    falls back to the first 24 chars of the user message."""

    def __init__(self, config: FsarConfig, store: SessionStore,
                 client_factory: Callable[[], tuple[Any, str]],
                 push_event: Callable[[dict], Awaitable[None]]) -> None:
        self._config = config
        self._store = store
        self._client_factory = client_factory
        self._push_event = push_event

    def schedule(self, conversation_id: str, first_message: str) -> None:
        """Fire-and-forget. No-op if no event loop is running."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.debug("title gen skipped: no running event loop")
            return
        task = loop.create_task(self._run(conversation_id, first_message))
        task.add_done_callback(self._on_done)

    def _on_done(self, task: asyncio.Task) -> None:
        try:
            task.result()
        except Exception as e:
            logger.warning(f"title gen task ended: {e}")

    async def _run(self, conversation_id: str, first_message: str) -> None:
        title = await self._generate(first_message)
        if not title:
            title = self._truncate(first_message)
        try:
            self._store.rename(conversation_id, title)
            await self._push_event({
                "type": "conversation.title_updated",
                "conversation_id": conversation_id,
                "title": title,
            })
        except Exception as e:
            logger.warning(f"title persist failed: {e}")

    async def _generate(self, text: str) -> str:
        try:
            client, model = self._client_factory()
        except Exception as e:
            logger.debug(f"title: client init failed: {e}")
            return ""
        if client is None or not model:
            return ""
        try:
            resp = await asyncio.to_thread(
                chat_completion,
                client,
                model=model,
                messages=[
                    {"role": "system", "content": TITLE_SYSTEM},
                    {"role": "user", "content": text[:600]},
                ],
                max_tokens=64,
                temperature=0.3,
            )
            content = (resp.choices[0].message.content or "")
            content = _strip_think(content)
            return self._clean(content)
        except Exception as e:
            logger.warning(f"title LLM call failed: {e}")
            return ""

    @staticmethod
    def _clean(raw: str) -> str:
        raw = raw.strip().strip('"\'`').strip()
        if "\n" in raw:
            raw = raw.split("\n", 1)[0].strip()
        return raw[:32].strip()

    @staticmethod
    def _truncate(text: str) -> str:
        text = text.strip().replace("\n", " ")
        if len(text) <= 24:
            return text
        return text[:23] + "…"
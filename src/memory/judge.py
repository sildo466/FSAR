# SPDX-License-Identifier: MIT
"""Per-candidate relevance judgment for memory injection."""

from __future__ import annotations

import hashlib
import json
from typing import Protocol

from src.memory.candidates import Candidate
from src.providers.judge.client import BatchFailed, JevClient
from src.utils.llm_factory import chat_completion


class MemoryJudge(Protocol):
    def score(
        self,
        query: str,
        candidates: list[Candidate],
        *,
        mode: str,
        context: str = "",
    ) -> dict[str, float]:
        """Return key -> 0..1 (higher = more worth injecting). Empty dict = no judgment."""
        ...


class NullJudge:
    """No judgment: the packer falls back to static priority order."""

    def score(self, query, candidates, *, mode, context=""):
        return {}


_AGENT_INSTRUCTION = (
    "Candidate [{key}] is worth spending part of a limited context budget on, given the "
    "user's question. Judge usefulness for answering THIS question only. Being a fact about "
    "the user does not by itself make it useful; being technical does not make it useless. "
    "A memory that only shares a topic word with the question is not useful."
)
_CHARACTER_INSTRUCTION = (
    "Item [{key}] is something this character could plausibly know or care about when "
    "talking to this user."
)

_CHARACTER_SYSTEM = """You are a memory filter for a character in a roleplay setting.
You receive (1) a character summary and (2) memory items, each with an ID.
Keep only items this character could plausibly know or care about when
interacting with this user.
Rules:
- KEEP facts about the user themselves: name, language, how they like to be
  talked to, life situation, emotional state.
- DROP technical skills, tool strategies, engineering preferences, task
  workflows, integration notes.
- Uncertain + about the user personally: keep.
- Uncertain + about tools or workflows: drop.
Return ONLY a JSON object: {"keep": ["F1", "P3"]} - IDs of kept items.
No rewriting, no commentary."""


class JevJudge:
    """Scores candidates through a JEV evaluation endpoint.

    A failed batch yields no scores rather than wrong ones, so the packer falls
    back to priority order for those items.
    """

    def __init__(self, client: JevClient, *, model: str = ""):
        self.client = client
        self.model = model

    def score(self, query, candidates, *, mode, context=""):
        if not candidates:
            return {}
        template = _CHARACTER_INSTRUCTION if mode == "character" else _AGENT_INSTRUCTION
        instructions = {c.key: template.format(key=c.key) for c in candidates}
        head = f"User question: {query}\n" if query else ""
        if context:
            head = f"{context}\n\n{head}"
        state = head + "Candidates:\n" + "\n".join(f"[{c.key}] {c.text}" for c in candidates)
        try:
            return self.client.nouls(state, instructions)
        except BatchFailed:
            return {}


class LlmJudge:
    """Character-mode persona filter over the active provider.

    Keeps the pre-JEV behaviour so a user without JEV configured does not
    silently lose persona filtering.
    """

    def __init__(self, client, model: str, provider_id: str, *,
                 cache: dict[str, set[str]] | None = None):
        self.client = client
        self.model = model
        self.provider_id = provider_id
        self.cache = cache

    def score(self, query, candidates, *, mode, context=""):
        if not candidates or not self.provider_id or not self.model:
            return {}
        payload = "\n".join(f"[{c.key}] {c.text}" for c in candidates)
        # `context` carries the character summary, so distinct characters never
        # share a cache entry.
        cache_key = hashlib.sha256(f"{context}\n{payload}".encode("utf-8")).hexdigest()
        if self.cache is not None and cache_key in self.cache:
            keep = self.cache[cache_key]
        else:
            try:
                resp = chat_completion(
                    self.client,
                    provider_id=self.provider_id,
                    model=self.model,
                    messages=[
                        {"role": "system", "content": _CHARACTER_SYSTEM},
                        {"role": "user", "content": f"{context}\n\n---\n{payload}"},
                    ],
                    max_tokens=100000,
                    stream=False,
                )
                text = (resp.choices[0].message.content or "").strip()
                if text.startswith("```"):
                    text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
                keep = {str(x) for x in json.loads(text.strip()).get("keep", [])}
            except Exception:
                return {}
            if self.cache is not None:
                self.cache[cache_key] = keep
        return {c.key: (1.0 if c.key in keep else 0.0) for c in candidates}

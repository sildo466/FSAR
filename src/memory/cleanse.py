"""LLM-cleansed memory for character mode.

Raw memory (user profile, preferences, patterns, history, saved facts) is
mostly engineering-flavored. Before injecting it into a character prompt, a
small LLM pass drops whatever the character has no business knowing, keeping
only items about the user themselves. Failures inject nothing — never raw.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from src.utils.llm_factory import chat_completion

_SECTION_PREFIX = {
    "[Saved Facts]": "F",
    "[User Profile]": "P",
    "[Known Preferences]": "R",
    "[Behavioral Patterns]": "T",
    "[Relevant History]": "H",
}

_SYSTEM = """You are a memory filter for a character in a roleplay setting.
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


def _tag_items(raw: str) -> list[tuple[str, str]]:
    """Number items per section: returns [(tag, text)] with tags F1/P1/R1/T1/H1."""
    tagged: list[tuple[str, str]] = []
    section = ""
    counters = {k: 0 for k in "FPRTH"}
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped in _SECTION_PREFIX:
            section = _SECTION_PREFIX[stripped]
            counters[section] = 0
            continue
        if not stripped:
            continue
        counters[section] = counters.get(section, 0) + 1
        tag = f"{section}{counters[section]}" if section else "X"
        tagged.append((tag, stripped))
    return tagged


def _character_summary(character: Any) -> str:
    return (
        f"Name: {character.name}\n"
        f"Description: {character.description}\n"
        f"Personality: {character.personality}\n"
        f"Scenario: {getattr(character, 'scenario', '')}"
    )


def _parse_keep(content: str) -> list[str]:
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip()).strip()
    data = json.loads(content)
    return [str(x) for x in data.get("keep", [])]


def cleanse_memory_block(
    raw: str,
    character: Any,
    client: Any,
    model: str,
    provider_id: str,
    *,
    cache: dict[tuple[int, str], str] | None = None,
) -> str:
    """LLM-filter `raw` memory for `character`. Kept lines returned verbatim.

    On any failure returns "" — never fall back to unfiltered memory.
    Cache keyed by (character id, sha256(raw)); pass a shared dict to reuse.
    """
    if not raw or character is None or getattr(character, "id", None) is None:
        return raw or ""
    key = (character.id, hashlib.sha256(raw.encode("utf-8")).hexdigest())
    if cache is not None and key in cache:
        return cache[key]

    tagged = _tag_items(raw)
    if not tagged:
        result = ""
    else:
        tagged_text = "\n".join(f"[{tag}] {text}" for tag, text in tagged)
        user_msg = f"{_character_summary(character)}\n\n---\n{tagged_text}"
        try:
            resp = chat_completion(
                client,
                provider_id=provider_id,
                model=model,
                messages=[
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": user_msg},
                ],
                max_tokens=2000,
                stream=False,
            )
            keep = set(_parse_keep(resp.choices[0].message.content))
        except Exception:
            keep = set()
        result = "\n".join(text for tag, text in tagged if tag in keep)

    if cache is not None:
        cache[key] = result
    return result

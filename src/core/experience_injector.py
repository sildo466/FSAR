"""FSAR ExperienceIndexInjector — build the ## Experiences index block for system prompt.

Mirrors the StrategyInjector pattern (P5.3). Reads from ExperienceStore,
gated by intensity:
- off      → empty block (no injection)
- low      → experiences index only
- medium   → experiences index + recent memory chunks
- high     → full index + memory chunks + active proposed-from-reflections hint

Compact categories (configured in user_model or settings.yaml) collapse the
desc to just the name — for power users who already know what's there.
"""

from __future__ import annotations

from typing import Iterable

from src.memory.experience_store import ExperienceStore
from src.utils.logger import logger


INTENSITY_OFF = "off"
INTENSITY_LOW = "low"
INTENSITY_MEDIUM = "medium"
INTENSITY_HIGH = "high"


class ExperienceIndexInjector:
    """Assemble the ## Experiences + ## Memory blocks for system prompt."""

    def __init__(self,
                 store: ExperienceStore | None = None,
                 *, intensity: str | None = None,
                 max_desc_chars: int = 60,
                 max_chunks: int = 5,
                 compact_categories: Iterable[str] | None = None):
        self.store = store or ExperienceStore()
        self.intensity = intensity or INTENSITY_OFF
        if self.intensity not in (INTENSITY_OFF, INTENSITY_LOW, INTENSITY_MEDIUM,
                                   INTENSITY_HIGH):
            raise ValueError(f"invalid intensity: {self.intensity!r}")
        self.max_desc_chars = max_desc_chars
        self.max_chunks = max_chunks
        self.compact_categories = set(compact_categories or [])

    def set_intensity(self, intensity: str) -> None:
        if intensity not in (INTENSITY_OFF, INTENSITY_LOW, INTENSITY_MEDIUM,
                             INTENSITY_HIGH):
            raise ValueError(f"invalid intensity: {intensity!r}")
        self.intensity = intensity

    def build_block(self) -> str:
        """Return the markdown block to inject. Empty when off."""
        if self.intensity == INTENSITY_OFF:
            return ""

        parts: list[str] = []
        try:
            from src.memory.skill_sync import sync_skills_from_disk
            sync_skills_from_disk(self.store)
        except Exception as e:
            logger.debug(f"skill disk sync skipped: {e}")

        try:
            exp_block = self.store.render_index(
                max_desc_chars=self.max_desc_chars,
                compact_categories=self.compact_categories,
            )
            if exp_block:
                parts.append(exp_block)
        except Exception as e:
            logger.debug(f"experience index skipped: {e}")

        if self.intensity in (INTENSITY_MEDIUM, INTENSITY_HIGH):
            try:
                mc_block = self.store.render_memory_chunks_block(limit=self.max_chunks)
                if mc_block:
                    parts.append(mc_block)
            except Exception as e:
                logger.debug(f"memory chunks block skipped: {e}")

        if not parts:
            return ""
        return "\n\n".join(parts) + "\n"

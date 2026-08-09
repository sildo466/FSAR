"""FSAR memory recall — unified interface.

The orchestrator calls recall_for_context(query) and gets back an
LLM-friendly context block containing:
- Relevant past conversations (semantic)
- User preferences
- Behavioral patterns
- User profile
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.memory.experience_store import ExperienceStore
from src.memory.feedback import FeedbackStore
from src.memory.long_term import LongTermMemory
from src.memory.semantic import SemanticMemory
from src.memory.user_model import UserModel
from src.utils.logger import logger


@dataclass
class RecallResult:
    """A single recall result."""
    similar_conversations: list[dict] = field(default_factory=list)
    preferences: dict[str, str] = field(default_factory=dict)
    patterns: list[dict] = field(default_factory=list)
    profile: dict[str, str] = field(default_factory=dict)
    memory_chunks: list[dict] = field(default_factory=list)

    def to_context(self, max_len: int = 2000) -> str:
        """Format as an LLM-friendly context block (injected into a system/user message)."""
        parts: list[str] = []
        if self.memory_chunks:
            parts.append("\n[Saved Facts]")
            parts.extend(
                f"- {c['title']}: {c['body']}" for c in self.memory_chunks[:8]
            )
        if self.profile:
            parts.append("\n[User Profile]")
            parts.extend(f"- {k}: {v}" for k, v in self.profile.items())
        if self.preferences:
            parts.append("\n[Known Preferences]")
            parts.extend(f"- {k}: {v}" for k, v in self.preferences.items())
        if self.patterns:
            parts.append("\n[Behavioral Patterns]")
            parts.extend(f"- {p['pattern']} (x{p['count']})" for p in self.patterns[:10])
        if self.similar_conversations:
            parts.append("\n[Relevant History]")
            for c in self.similar_conversations[:5]:
                parts.append(f"- {c.get('text', '')[:200]}")

        text = "\n".join(parts)
        if len(text) > max_len:
            text = text[:max_len] + "..."
        return text

    @property
    def is_empty(self) -> bool:
        return not (self.profile or self.preferences or self.patterns
                    or self.similar_conversations or self.memory_chunks)


class MemoryRecall:
    """Unified entry point for memory recall."""

    def __init__(self,
                 long_term: LongTermMemory | None = None,
                 semantic: SemanticMemory | None = None,
                 user_model: UserModel | None = None,
                 feedback: FeedbackStore | None = None,
                 experience_store: ExperienceStore | None = None):
        self.long_term = long_term or LongTermMemory()
        self.semantic = semantic or SemanticMemory()
        self.user_model = user_model or UserModel()
        self.feedback = feedback or FeedbackStore()
        self.experience_store = experience_store or ExperienceStore()

    def recall_for_context(self, query: str, *,
                           include_semantic: bool = True,
                           semantic_top_k: int = 5) -> RecallResult:
        """Recall memories relevant to query — used for injecting into LLM context."""
        result = RecallResult()

        # Profile & preferences & patterns (cheap, always fetched)
        result.profile = self.user_model.get_profile()
        prefs = self.user_model.get_all_preferences()
        result.preferences = {k: p.value for k, p in prefs.items()}
        result.patterns = self.user_model.get_top_patterns(limit=10)

        # Saved facts (P6 memory_chunks) — keyword search; cheap
        if query.strip():
            try:
                hits = self.experience_store.search_chunks(query, limit=5)
                result.memory_chunks = [
                    {"title": c.title, "body": c.body, "source": c.source}
                    for c in hits
                ]
            except Exception as e:
                logger.debug(f"memory_chunks recall failed: {e}")

        # Semantic recall
        if include_semantic and query.strip():
            try:
                hits = self.semantic.search(query, n=semantic_top_k)
                result.similar_conversations = [
                    {
                        "text": h.text,
                        "metadata": h.metadata,
                        "distance": h.distance,
                    }
                    for h in hits
                ]
            except Exception as e:
                logger.warning(f"Semantic recall failed: {e}")

        return result

    def remember(self, text: str, *, session_id: str = "",
                 role: str = "user", tags: list[str] | None = None) -> str:
        """Proactively store into semantic memory. Returns doc_id."""
        try:
            return self.semantic.add(
                text, session_id=session_id, role=role, tags=tags,
            )
        except Exception as e:
            logger.warning(f"Semantic remember failed: {e}")
            return ""

    def stats(self) -> dict:
        """Memory system overview."""
        long_stats = self.long_term.get_stats()
        return {
            "long_term": long_stats,
            "semantic_count": self.semantic.count(),
            "semantic_available": self.semantic.available,
            "preferences_count": len(self.user_model.get_all_preferences()),
            "patterns_count": len(self.user_model.get_top_patterns(limit=999)),
            "profile_count": len(self.user_model.get_profile()),
            "feedback": self.feedback.get_stats(),
        }
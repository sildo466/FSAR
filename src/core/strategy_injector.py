"""FSAR StrategyInjector — synthesize ## Learned Strategies for system prompt.

Combines three signal sources, each gated by intensity:
- Tool decision-log stats (success_rate / avg_latency) → "Prefer X over Y"
- User model preferences (explicit + reflection-sourced)
- Task reflection suggested_strategy entries (only at intensity=high)

Output: a markdown-formatted block appended to the LLM system prompt.
"""

from __future__ import annotations

from typing import Iterable

from src.memory.decision_log import DecisionLog
from src.memory.user_model import UserModel
from src.utils.config import get_config
from src.utils.logger import logger


INTENSITY_OFF = "off"
INTENSITY_LOW = "low"
INTENSITY_MEDIUM = "medium"
INTENSITY_HIGH = "high"


class StrategyInjector:
    """Build the '## Learned Strategies' system-prompt block.

    Args:
        intensity: gate how much to inject (matches reflection_intensity by default)
        max_prefs: max number of preferences to surface
        max_strategies: max number of task-reflection strategies
        success_rate_threshold: success_rate below which a tool is "avoid"
        latency_threshold_ms: latency above which a tool is "slow"
        min_uses: min tool_stats uses before a tool surfaces in strategies
    """

    def __init__(self,
                 decision_log: DecisionLog | None = None,
                 user_model: UserModel | None = None,
                 intensity: str | None = None,
                 max_prefs: int = 5,
                 max_strategies: int = 5,
                 success_rate_threshold: float = 70.0,
                 latency_threshold_ms: float = 5000.0,
                 min_uses: int = 3):
        self.decision_log = decision_log or DecisionLog()
        self.user_model = user_model or UserModel()
        if intensity is None:
            intensity = get_config().reflection_intensity
        if intensity not in (INTENSITY_OFF, INTENSITY_LOW,
                            INTENSITY_MEDIUM, INTENSITY_HIGH):
            raise ValueError(f"invalid intensity: {intensity!r}")
        self.intensity = intensity
        self.max_prefs = max_prefs
        self.max_strategies = max_strategies
        self.success_rate_threshold = success_rate_threshold
        self.latency_threshold_ms = latency_threshold_ms
        self.min_uses = min_uses

    def set_intensity(self, intensity: str) -> None:
        if intensity not in (INTENSITY_OFF, INTENSITY_LOW,
                            INTENSITY_MEDIUM, INTENSITY_HIGH):
            raise ValueError(f"invalid intensity: {intensity!r}")
        self.intensity = intensity

    def build_block(self, *, recent_strategies: Iterable[str] = ()) -> str:
        """Return the markdown block to inject. Empty string if off / no data."""
        if self.intensity == INTENSITY_OFF:
            return ""

        lines: list[str] = []
        # 1) Tool stats (medium + high)
        if self.intensity in (INTENSITY_MEDIUM, INTENSITY_HIGH):
            lines.extend(self._tool_stat_lines())

        # 2) Reflection-derived user preferences (always on for non-off)
        pref_lines = self._preference_lines()
        if pref_lines:
            lines.extend(pref_lines)

        # 3) Task-reflection suggested_strategy (only high)
        if self.intensity == INTENSITY_HIGH:
            strat = list(recent_strategies)[:self.max_strategies]
            if strat:
                lines.append("\nLearned task strategies:")
                for s in strat:
                    s = s.strip()
                    if s:
                        lines.append(f"- {s}")

        if not lines or all(not l for l in lines):
            return ""

        return "## Learned Strategies (from past interactions)\n" + "\n".join(lines) + "\n"

    def _tool_stat_lines(self) -> list[str]:
        stats = self.decision_log.get_stats(min_uses=self.min_uses)
        out: list[str] = []
        for s in stats:
            tool = s["tool_name"]
            uses = s["total_uses"]
            rate = s["success_rate_pct"]
            avg_ms = s["avg_latency_ms"] or 0.0
            if rate is not None and rate < self.success_rate_threshold:
                failures = self.decision_log.get_top_failure_modes(tool, limit=2)
                hint = f"common errors: {', '.join(failures)}" if failures else "low success rate"
                out.append(
                    f"- Avoid `{tool}` when possible ({rate:.0f}% success over {uses} uses — {hint})"
                )
            elif avg_ms > self.latency_threshold_ms:
                out.append(
                    f"- `{tool}` is slow (avg {avg_ms:.0f}ms over {uses} uses) — batch calls when possible"
                )
        return out

    def _preference_lines(self) -> list[str]:
        prefs = self.user_model.get_all_preferences()
        # Surface only "explicit" + "reflection" / "task_reflection" sources
        surfaced: list[tuple[str, str]] = []
        for k, p in prefs.items():
            if k.startswith("_"):
                continue
            if p.source not in ("explicit", "reflection", "task_reflection", "inferred"):
                continue
            if not p.value:
                continue
            surfaced.append((k, p.value))
        surfaced.sort(key=lambda x: (
            0 if x[1].startswith("task_strategy::") else 1,
            x[0],
        ))
        surfaced = surfaced[:self.max_prefs]
        if not surfaced:
            return []
        out = ["User preferences:"]
        for k, v in surfaced:
            short_k = k.replace("task_strategy::", "").strip()
            out.append(f"- {short_k}: {v}")
        return out
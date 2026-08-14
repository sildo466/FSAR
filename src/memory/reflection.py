"""FSAR reflection mechanism — consolidates history during idle + per-task.

Trigger modes (controlled by `reflection.intensity`):
- per_task:    orchestrator invokes after each task completion / failure
- on_failure:  triggered when task exits with error / timeout / low rating
- idle_batch:  accumulated N messages or N hours since last reflection

Reflection actions:
- Aggregate ratings (high/low samples)
- Cluster user preferences from conversation content
- Ask LLM to extract user profile
- Write back to user_model.profile / preferences / patterns
- Per-task: capture failure modes and suggested strategy adjustments
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from src.memory.feedback import FeedbackStore
from src.memory.long_term import LongTermMemory
from src.memory.user_model import UserModel
from src.utils.config import get_config
from src.utils.logger import logger
from src.utils.llm_factory import chat_completion


REFLECTION_PROMPT = """You are FSAR's reflection assistant. Based on the user's conversation history and rating feedback,
extract a stable profile and preferences for this user, used to personalize future conversations.

[High-rated reply samples] (rating >= 4, reflects what the user likes)
{high_samples}

[Low-rated reply samples] (rating <= 2, reflects what the user dislikes)
{low_samples}

[Recent conversation excerpts]
{recent_excerpts}

Output strict JSON only (no other text, no markdown wrappers):
{{
  "profile": {{
    "<profile_key>": "<profile_description>"
  }},
  "preferences": {{
    "<preference_key>": "<preference_value>"
  }},
  "patterns": [
    {{"pattern": "<behavioral_pattern>", "evidence": "<evidence>"}}
  ]
}}

Requirements:
- profile: user's personality / habits / communication style (e.g. "prefers concise replies", "often codes in the evening")
- preferences: specific preferences for tools / formats / language (e.g. "uses VSCode", "replies in English")
- patterns: recurring behaviors (e.g. "often uses file_ops to organize downloads")
- If there is not enough evidence, leave the corresponding field empty. Do not fabricate.
"""


TASK_REFLECTION_PROMPT = """You are FSAR's per-task reflection assistant. Analyze ONE completed task and extract:
- failure_modes: what went wrong (or what could have gone wrong)
- success_patterns: what worked well and should be repeated
- suggested_strategy: a concrete hint for future similar tasks (1-2 sentences, imperative form)

[Task]
{task}

[Outcome] {outcome} | steps={step_count} | tools_used={tools_used} | errors={error_count}

[Action history (truncated)]
{history_excerpt}

Output strict JSON only:
{{
  "failure_modes": ["<mode>", ...],
  "success_patterns": ["<pattern>", ...],
  "suggested_strategy": "<one-line imperative hint>"
}}

Rules:
- Be specific (mention concrete tool names / actions), not generic platitudes
- If outcome was success, failure_modes may be empty
- suggested_strategy must be actionable, e.g. "Prefer app_control over computer_use for WeChat message tasks"
"""


@dataclass
class ReflectionReport:
    """Output of an idle / batch reflection pass."""
    profile: dict[str, str]
    preferences: dict[str, str]
    patterns: list[dict]
    generated_at: datetime

    def to_dict(self) -> dict:
        return {
            "profile": self.profile,
            "preferences": self.preferences,
            "patterns": self.patterns,
            "generated_at": self.generated_at.isoformat(),
        }


@dataclass
class TaskReflection:
    """Output of a per-task reflection pass."""
    task_id: str
    outcome: str
    failure_modes: list[str]
    success_patterns: list[str]
    suggested_strategy: str
    step_count: int
    tools_used: list[str]
    error_count: int
    generated_at: datetime

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "outcome": self.outcome,
            "failure_modes": self.failure_modes,
            "success_patterns": self.success_patterns,
            "suggested_strategy": self.suggested_strategy,
            "step_count": self.step_count,
            "tools_used": self.tools_used,
            "error_count": self.error_count,
            "generated_at": self.generated_at.isoformat(),
        }


class ReflectionStore:
    """SQLite persistence for task_reflections table."""

    def __init__(self, db_path: str | Path | None = None):
        config = get_config()
        self._db_path = Path(db_path or config.memory_sqlite_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS task_reflections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    failure_modes TEXT NOT NULL DEFAULT '[]',
                    success_patterns TEXT NOT NULL DEFAULT '[]',
                    suggested_strategy TEXT NOT NULL DEFAULT '',
                    step_count INTEGER NOT NULL DEFAULT 0,
                    tools_used TEXT NOT NULL DEFAULT '[]',
                    error_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_task_reflections_session "
                "ON task_reflections(session_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_task_reflections_created "
                "ON task_reflections(created_at)"
            )
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def save(self, ref: TaskReflection, session_id: str) -> int:
        now = ref.generated_at.isoformat()
        with self._connect() as conn:
            cur = conn.execute("""
                INSERT INTO task_reflections (
                    task_id, session_id, outcome, failure_modes,
                    success_patterns, suggested_strategy,
                    step_count, tools_used, error_count, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ref.task_id, session_id, ref.outcome,
                json.dumps(ref.failure_modes, ensure_ascii=False),
                json.dumps(ref.success_patterns, ensure_ascii=False),
                ref.suggested_strategy,
                ref.step_count,
                json.dumps(ref.tools_used, ensure_ascii=False),
                ref.error_count, now,
            ))
            conn.commit()
            return cur.lastrowid

    def list_recent(self, limit: int = 20,
                    session_id: str | None = None) -> list[dict]:
        with self._connect() as conn:
            if session_id:
                rows = conn.execute("""
                    SELECT id, task_id, session_id, outcome, failure_modes,
                           success_patterns, suggested_strategy,
                           step_count, tools_used, error_count, created_at
                    FROM task_reflections
                    WHERE session_id = ?
                    ORDER BY created_at DESC LIMIT ?
                """, (session_id, limit)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT id, task_id, session_id, outcome, failure_modes,
                           success_patterns, suggested_strategy,
                           step_count, tools_used, error_count, created_at
                    FROM task_reflections
                    ORDER BY created_at DESC LIMIT ?
                """, (limit,)).fetchall()
        out = []
        for r in rows:
            out.append({
                "id": r[0],
                "task_id": r[1],
                "session_id": r[2],
                "outcome": r[3],
                "failure_modes": json.loads(r[4] or "[]"),
                "success_patterns": json.loads(r[5] or "[]"),
                "suggested_strategy": r[6],
                "step_count": r[7],
                "tools_used": json.loads(r[8] or "[]"),
                "error_count": r[9],
                "created_at": r[10],
            })
        return out

    def get_stats(self) -> dict:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM task_reflections").fetchone()[0]
            failures = conn.execute(
                "SELECT COUNT(*) FROM task_reflections WHERE outcome != 'success'"
            ).fetchone()[0]
        return {"total": total, "failures": failures}


class IdleReflector:
    """Idle-time reflection — aggregate history + ratings + LLM inference."""

    REFLECTION_STATE_KEY = "_last_reflection_at"
    DEFAULT_INTERVAL_HOURS = 12.0

    def __init__(self,
                 long_term: LongTermMemory | None = None,
                 user_model: UserModel | None = None,
                 feedback: FeedbackStore | None = None,
                 llm_client=None,
                 model: str | None = None,
                 interval_hours: float = DEFAULT_INTERVAL_HOURS,
                 intensity: str = "medium"):
        self.long_term = long_term or LongTermMemory()
        self.user_model = user_model or UserModel()
        self.feedback = feedback or FeedbackStore()
        self._llm = llm_client
        self._model = model
        self.interval_hours = interval_hours
        self.intensity = intensity
        self._events_since_reflect = 0

    def set_llm(self, llm_client):
        """Lazily inject the LLM client."""
        self._llm = llm_client

    def set_intensity(self, intensity: str) -> None:
        if intensity not in VALID_INTENSITIES:
            raise ValueError(f"intensity must be one of {VALID_INTENSITIES}, got {intensity!r}")
        self.intensity = intensity

    def should_reflect_by_triggers(self, triggers: dict | None) -> bool:
        """GUI-driven trigger: per-task/on_failure are handled by TaskReflector;
        idle_batch is ours. Returns True if idle_batch thresholds are met."""
        cfg = (triggers or {}).get("idle_batch") or {}
        if not cfg.get("enabled"):
            return False
        threshold_events = int(cfg.get("threshold_events") or 0)
        if threshold_events > 0 and self._events_since_reflect >= threshold_events:
            return True
        threshold_hours = float(cfg.get("threshold_hours") or 0)
        if threshold_hours > 0:
            last = self.last_reflection_at()
            if last is None:
                return True
            if (datetime.now() - last).total_seconds() >= threshold_hours * 3600:
                return True
        return False

    def bump_event(self) -> None:
        self._events_since_reflect += 1

    def should_reflect(self) -> bool:
        """Should we reflect now? Based on last reflection time + data volume."""
        last = self.user_model.get_preference(self.REFLECTION_STATE_KEY)
        now = datetime.now()
        if last:
            try:
                last_dt = datetime.fromisoformat(last)
                if now - last_dt < timedelta(hours=self.interval_hours):
                    return False
            except Exception:
                pass

        stats = self.long_term.get_stats()
        return stats["total_messages"] >= 10

    def mark_done(self):
        """Mark a reflection as just completed."""
        self._events_since_reflect = 0
        self.user_model.set_preference(
            self.REFLECTION_STATE_KEY,
            datetime.now().isoformat(),
            source="system",
        )

    def last_reflection_at(self) -> datetime | None:
        """Last reflection timestamp (for UI display)."""
        last = self.user_model.get_preference(self.REFLECTION_STATE_KEY)
        if not last:
            return None
        try:
            return datetime.fromisoformat(last)
        except Exception:
            return None

    def reflect(self, *, force: bool = False,
                max_samples: int = 10) -> ReflectionReport | None:
        """Run reflection. force=True skips the interval check."""
        if not force and not self.should_reflect():
            logger.info("Reflection skipped (interval not reached or insufficient data)")
            return None

        high = self.feedback.get_high_rated(limit=max_samples)
        low = self.feedback.get_low_rated(limit=max_samples)
        recent = self.long_term.get_recent(limit=30)

        if self._llm:
            report = self._llm_reflection(high, low, recent)
            if report is None:
                logger.warning("LLM reflection returned None, falling back to rules")
                report = self._rule_based_reflection(high, low, recent)
        else:
            logger.warning("No LLM configured; using rule-based reflection")
            report = self._rule_based_reflection(high, low, recent)

        for k, v in report.profile.items():
            self.user_model.set_profile(k, v, source="reflection")
        for k, v in report.preferences.items():
            self.user_model.set_preference(k, v, source="reflection", confidence=0.7)
        for p in report.patterns:
            self.user_model.record_pattern(
                p.get("pattern", ""), p.get("evidence", ""),
            )

        self.mark_done()
        logger.info(f"Reflection complete: {len(report.profile)} profile, "
                    f"{len(report.preferences)} preferences, "
                    f"{len(report.patterns)} patterns")

        if self.intensity == INTENSITY_HIGH:
            try:
                from src.memory.experience_store import ExperienceStore
                promoted = ExperienceStore().auto_promote(threshold=3)
                if promoted:
                    logger.info(
                        f"auto_promote: created {promoted} experience row(s) "
                        f"from >=3-occurrence task_reflection clusters"
                    )
            except Exception as e:
                logger.debug(f"auto_promote skipped: {e}")

        return report

    def _rule_based_reflection(self, high: list, low: list,
                               recent: list) -> ReflectionReport:
        profile: dict[str, str] = {}
        prefs: dict[str, str] = {}

        if high and not low:
            profile["feedback_signal"] = f"User gave {len(high)} high ratings, no lows — overall satisfied"
        elif low and not high:
            profile["feedback_signal"] = f"User gave {len(low)} low ratings — improvement needed"
        elif high and low:
            profile["feedback_signal"] = (
                f"Mixed ratings (high {len(high)} / low {len(low)}) — inconsistent style"
            )

        reasons = [r.get("reason", "").strip() for r in low if r.get("reason")]
        if reasons:
            profile["common_complaints"] = " / ".join(reasons[:5])

        high_reasons = [r.get("reason", "").strip()
                        for r in high if r.get("reason")]
        if high_reasons:
            profile["common_praise"] = " / ".join(high_reasons[:5])

        return ReflectionReport(
            profile=profile,
            preferences=prefs,
            patterns=[],
            generated_at=datetime.now(),
        )

    def _llm_reflection(self, high: list, low: list,
                        recent: list) -> ReflectionReport | None:
        high_text = self._format_samples(high[:5])
        low_text = self._format_samples(low[:5])
        recent_text = "\n".join(
            f"[{r.role}] {r.content[:200]}" for r in recent[-20:]
        )

        prompt = REFLECTION_PROMPT.format(
            high_samples=high_text or "(none)",
            low_samples=low_text or "(none)",
            recent_excerpts=recent_text or "(none)",
        )

        try:
            model = self._model
            if not model:
                from src.utils.config import get_config
                model = get_config().get_active_provider().get("model", "")
            resp = chat_completion(
                self._llm,
                model=model,
                messages=[
                    {"role": "system", "content": "You are a data analyst. Output JSON only."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=2000,
                temperature=0.3,
            )
            text = (resp.choices[0].message.content or "").strip()
            return self._parse_json_report(text)
        except Exception as e:
            logger.warning(f"LLM reflection failed: {e}")
            return None

    def _format_samples(self, samples: list[dict]) -> str:
        if not samples:
            return ""
        lines = []
        for s in samples:
            line = f"Rated {s['rating']}/5"
            if s.get("reason"):
                line += f" (reason: {s['reason']})"
            line += f": {s['content'][:150]}"
            lines.append(line)
        return "\n".join(lines)

    def _parse_json_report(self, text: str) -> ReflectionReport | None:
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            return None
        try:
            data = json.loads(m.group())
        except json.JSONDecodeError:
            return None

        return ReflectionReport(
            profile=data.get("profile", {}) or {},
            preferences=data.get("preferences", {}) or {},
            patterns=data.get("patterns", []) or [],
            generated_at=datetime.now(),
        )


INTENSITY_OFF = "off"
INTENSITY_LOW = "low"
INTENSITY_MEDIUM = "medium"
INTENSITY_HIGH = "high"
VALID_INTENSITIES = {INTENSITY_OFF, INTENSITY_LOW, INTENSITY_MEDIUM, INTENSITY_HIGH}


class TaskReflector:
    """Per-task reflection — invoked by orchestrator on task completion / failure.

    Three trigger modes (independent flags from GUI):
    - per_task:    always invoked after a task (highest learning cadence)
    - on_failure:  only on failure / timeout / low-rating
    - idle_batch:  collected by IdleReflector (separate class)
    """

    def __init__(self,
                 store: ReflectionStore | None = None,
                 user_model: UserModel | None = None,
                 llm_client=None,
                 model: str | None = None,
                 intensity: str = INTENSITY_MEDIUM,
                 triggers: dict | None = None):
        if intensity not in VALID_INTENSITIES:
            raise ValueError(f"intensity must be one of {VALID_INTENSITIES}, got {intensity!r}")
        self.store = store or ReflectionStore()
        self.user_model = user_model or UserModel()
        self._llm = llm_client
        self._model = model
        self.intensity = intensity
        self.triggers = triggers or {}

    def set_llm(self, llm_client):
        self._llm = llm_client

    def set_intensity(self, intensity: str):
        if intensity not in VALID_INTENSITIES:
            raise ValueError(f"intensity must be one of {VALID_INTENSITIES}, got {intensity!r}")
        self.intensity = intensity

    def set_triggers(self, triggers: dict) -> None:
        self.triggers = triggers or {}

    @property
    def per_task_enabled(self) -> bool:
        t = self.triggers.get("per_task")
        if t is None:
            return self.intensity in (INTENSITY_MEDIUM, INTENSITY_HIGH)
        return bool(t)

    @property
    def on_failure_enabled(self) -> bool:
        t = self.triggers.get("on_failure")
        if t is None:
            return self.intensity in (INTENSITY_LOW, INTENSITY_MEDIUM, INTENSITY_HIGH)
        return bool(t)

    @property
    def writeback_enabled(self) -> bool:
        return self.intensity == INTENSITY_HIGH

    def should_reflect(self, *, outcome: str) -> bool:
        """Decide whether to run reflection based on triggers + intensity + outcome."""
        if self.intensity == INTENSITY_OFF:
            return False
        if outcome == "success":
            return self.per_task_enabled
        return self.on_failure_enabled

    def reflect(self, *, task_id: str, session_id: str,
                task: str, outcome: str,
                history: list[dict],
                forced: bool = False) -> TaskReflection | None:
        """Run per-task reflection. Returns TaskReflection or None if skipped.

        Args:
            task: original user task description
            outcome: 'success' | 'failure' | 'timeout' | 'low_rating'
            history: list of step dicts from orchestrator
            forced: skip intensity check (e.g. manual CLI invocation)
        """
        if not forced and not self.should_reflect(outcome=outcome):
            logger.debug(f"Task reflection skipped (intensity={self.intensity}, outcome={outcome})")
            return None

        step_count = len(history)
        tools_used = self._extract_tools(history)
        error_count = sum(1 for h in history if h.get("error"))
        history_excerpt = self._format_history(history[-15:])

        if self._llm:
            report = self._llm_reflect(task, outcome, step_count, tools_used,
                                       error_count, history_excerpt)
            if report is None:
                report = self._rule_based_reflect(task, outcome, step_count,
                                                  tools_used, error_count, history)
        else:
            report = self._rule_based_reflect(task, outcome, step_count,
                                              tools_used, error_count, history)

        report.task_id = task_id
        self.store.save(report, session_id=session_id)

        if self.writeback_enabled and report.suggested_strategy:
            pref_key = f"task_strategy::{task_id}"
            self.user_model.set_preference(pref_key, report.suggested_strategy,
                                           source="task_reflection", confidence=0.6)

        logger.info(
            f"Task reflection saved: task={task_id} outcome={outcome} "
            f"failure_modes={len(report.failure_modes)} "
            f"strategy={report.suggested_strategy[:80]!r}"
        )
        return report

    @staticmethod
    def _extract_tools(history: list[dict]) -> list[str]:
        seen: list[str] = []
        for h in history:
            tool = h.get("action")
            if tool and tool not in seen:
                seen.append(tool)
        return seen

    @staticmethod
    def _format_history(history: list[dict]) -> str:
        if not history:
            return "(empty)"
        lines = []
        for h in history:
            step = h.get("step", "?")
            action = h.get("action", "?")
            params = h.get("params", {})
            result = h.get("result", "")
            error = h.get("error", "")
            line = f"#{step} {action}({json.dumps(params, ensure_ascii=False)[:80]})"
            if error:
                line += f" ERROR={error[:80]}"
            elif result:
                line += f" -> {result[:60]}"
            lines.append(line)
        return "\n".join(lines)

    def _rule_based_reflect(self, task: str, outcome: str, step_count: int,
                            tools_used: list[str], error_count: int,
                            history: list[dict]) -> TaskReflection:
        failure_modes: list[str] = []
        success_patterns: list[str] = []

        if error_count >= 2:
            failure_modes.append(
                f"{error_count} errors across {step_count} steps — repeated tool failures"
            )

        same_action_errors: dict[str, int] = {}
        for h in history:
            if h.get("error"):
                action = h.get("action", "?")
                same_action_errors[action] = same_action_errors.get(action, 0) + 1
        for action, n in same_action_errors.items():
            if n >= 2:
                failure_modes.append(
                    f"Repeated {action} failure ({n} times) — strategy not adapting"
                )

        if step_count > 20 and outcome != "success":
            failure_modes.append(
                f"Task ran {step_count} steps without success — possibly stuck loop"
            )

        if outcome == "success" and step_count <= 5:
            success_patterns.append(
                f"Efficient completion in {step_count} steps with {', '.join(tools_used[:3])}"
            )

        if error_count == 0 and outcome == "success":
            success_patterns.append(
                f"Zero-error run using {', '.join(tools_used[:3])}"
            )

        if outcome == "success" and not failure_modes:
            suggested = f"Continue using {tools_used[0] if tools_used else 'current approach'} for similar tasks"
        elif failure_modes:
            suggested = (
                f"For similar tasks, avoid {tools_used[0] if tools_used else 'problematic tools'} "
                f"and consider an alternative approach"
            )
        else:
            suggested = ""

        return TaskReflection(
            task_id="",
            outcome=outcome,
            failure_modes=failure_modes,
            success_patterns=success_patterns,
            suggested_strategy=suggested,
            step_count=step_count,
            tools_used=tools_used,
            error_count=error_count,
            generated_at=datetime.now(),
        )

    def _llm_reflect(self, task: str, outcome: str, step_count: int,
                     tools_used: list[str], error_count: int,
                     history_excerpt: str) -> TaskReflection | None:
        prompt = TASK_REFLECTION_PROMPT.format(
            task=task[:500],
            outcome=outcome,
            step_count=step_count,
            tools_used=", ".join(tools_used) or "(none)",
            error_count=error_count,
            history_excerpt=history_excerpt[:3000],
        )
        try:
            model = self._model
            if not model:
                from src.utils.config import get_config
                model = get_config().get_active_provider().get("model", "")
            resp = chat_completion(
                self._llm,
                model=model,
                messages=[
                    {"role": "system", "content": "You are a task post-mortem analyst. Output JSON only."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=100000,
                temperature=0.2,
            )
            text = (resp.choices[0].message.content or "").strip()
            return self._parse_json(text, outcome, step_count, tools_used, error_count)
        except Exception as e:
            logger.warning(f"LLM task reflection failed: {e}")
            return None

    @staticmethod
    def _parse_json(text: str, outcome: str, step_count: int,
                    tools_used: list[str], error_count: int) -> TaskReflection | None:
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            return None
        try:
            data = json.loads(m.group())
        except json.JSONDecodeError:
            return None
        return TaskReflection(
            task_id="",
            outcome=outcome,
            failure_modes=list(data.get("failure_modes", []) or []),
            success_patterns=list(data.get("success_patterns", []) or []),
            suggested_strategy=str(data.get("suggested_strategy", "") or ""),
            step_count=step_count,
            tools_used=tools_used,
            error_count=error_count,
            generated_at=datetime.now(),
        )
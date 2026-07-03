"""Tests for TaskReflector + ReflectionStore (Phase 5.1)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.memory.reflection import (
    TaskReflector,
    ReflectionStore,
    TaskReflection,
    INTENSITY_OFF,
    INTENSITY_LOW,
    INTENSITY_MEDIUM,
    INTENSITY_HIGH,
)


class FakeLLM:
    """Stub LLM that returns a canned reflection JSON."""

    def __init__(self, response: dict):
        self.response = response
        self.calls: list[dict] = []

        class _ChatCompletions:
            def __init__(self, outer):
                self.outer = outer

            def create(self, **kwargs):
                self.outer.calls.append(kwargs)

                class _Resp:
                    def __init__(self, content):
                        self.choices = [type("C", (), {
                            "message": type("M", (), {"content": content})()
                        })()]

                import json as _json
                return _Resp(_json.dumps(self.outer.response))

        self.chat = type("Chat", (), {"completions": _ChatCompletions(self)})()


def _tmp_db():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    return f.name


def test_intensity_validation():
    """Invalid intensity must be rejected at construction time."""
    try:
        TaskReflector(intensity="nonsense")
    except ValueError:
        return
    raise AssertionError("expected ValueError for invalid intensity")


def test_intensity_off_skips_all():
    """intensity=off should skip every reflection, including failures."""
    db = _tmp_db()
    store = ReflectionStore(db_path=db)
    reflector = TaskReflector(store=store, intensity=INTENSITY_OFF)
    for outcome in ("success", "failure", "timeout"):
        assert reflector.should_reflect(outcome=outcome) is False
        result = reflector.reflect(
            task_id=f"t_{outcome}",
            session_id="s1",
            task="dummy",
            outcome=outcome,
            history=[],
        )
        assert result is None
    assert store.get_stats()["total"] == 0


def test_low_intensity_skips_success():
    """intensity=low: only on_failure triggers, success is skipped."""
    db = _tmp_db()
    store = ReflectionStore(db_path=db)
    reflector = TaskReflector(store=store, intensity=INTENSITY_LOW)

    assert reflector.should_reflect(outcome="success") is False
    assert reflector.should_reflect(outcome="failure") is True
    assert reflector.should_reflect(outcome="timeout") is True

    reflector.reflect(task_id="t1", session_id="s1", task="x",
                     outcome="success", history=[])
    assert store.get_stats()["total"] == 0

    reflector.reflect(task_id="t2", session_id="s1", task="x",
                     outcome="failure", history=[
                         {"step": 1, "action": "click", "error": "timeout"},
                         {"step": 2, "action": "click", "error": "timeout"},
                     ])
    assert store.get_stats()["total"] == 1
    assert store.get_stats()["failures"] == 1


def test_medium_intensity_reflects_all():
    """intensity=medium: per_task on + on_failure on."""
    db = _tmp_db()
    store = ReflectionStore(db_path=db)
    reflector = TaskReflector(store=store, intensity=INTENSITY_MEDIUM)

    assert reflector.should_reflect(outcome="success") is True
    assert reflector.should_reflect(outcome="failure") is True

    reflector.reflect(task_id="t1", session_id="s1", task="x",
                     outcome="success", history=[])
    reflector.reflect(task_id="t2", session_id="s1", task="x",
                     outcome="failure", history=[])
    assert store.get_stats()["total"] == 2
    assert store.get_stats()["failures"] == 1


def test_rule_based_detects_repeated_failures():
    """Rule-based reflection must surface repeated same-tool failures."""
    db = _tmp_db()
    store = ReflectionStore(db_path=db)
    reflector = TaskReflector(store=store, intensity=INTENSITY_HIGH)

    history = [
        {"step": 1, "action": "click", "params": {"x": 100, "y": 200}, "error": "timeout"},
        {"step": 2, "action": "click", "params": {"x": 110, "y": 210}, "error": "timeout"},
        {"step": 3, "action": "click", "params": {"x": 120, "y": 220}, "error": "timeout"},
    ]
    ref = reflector.reflect(task_id="t1", session_id="s1",
                            task="click on button", outcome="failure",
                            history=history)
    assert ref is not None
    assert ref.error_count == 3
    assert ref.step_count == 3
    assert "click" in ref.tools_used
    assert any("Repeated" in m and "click" in m for m in ref.failure_modes), \
        f"Expected 'Repeated click failure' in {ref.failure_modes}"
    assert ref.suggested_strategy  # non-empty suggestion


def test_rule_based_detects_efficient_success():
    """Rule-based reflection must flag efficient success patterns."""
    db = _tmp_db()
    store = ReflectionStore(db_path=db)
    reflector = TaskReflector(store=store, intensity=INTENSITY_HIGH)

    history = [
        {"step": 1, "action": "launch_app", "result": "success"},
        {"step": 2, "action": "click", "params": {"x": 50, "y": 50}, "result": "success"},
    ]
    ref = reflector.reflect(task_id="t1", session_id="s1",
                            task="open notepad", outcome="success",
                            history=history)
    assert ref is not None
    assert ref.error_count == 0
    assert any("Efficient" in p or "Zero-error" in p
               for p in ref.success_patterns), \
        f"Expected efficiency pattern in {ref.success_patterns}"


def test_llm_reflection_used_when_available():
    """When LLM is configured, TaskReflector should call it and use parsed result."""
    db = _tmp_db()
    store = ReflectionStore(db_path=db)
    llm = FakeLLM({
        "failure_modes": ["screen capture race"],
        "success_patterns": ["short retry loop"],
        "suggested_strategy": "Add a 200ms sleep before screen capture.",
    })
    reflector = TaskReflector(
        store=store, intensity=INTENSITY_HIGH,
        llm_client=llm, model="test-model",
    )
    ref = reflector.reflect(
        task_id="t1", session_id="s1",
        task="some UI task", outcome="failure",
        history=[{"step": 1, "action": "click", "error": "capture failed"}],
    )
    assert ref is not None
    assert "screen capture race" in ref.failure_modes
    assert ref.suggested_strategy.startswith("Add a 200ms sleep")
    assert len(llm.calls) == 1
    assert llm.calls[0]["model"] == "test-model"


def test_writeback_only_on_high():
    """high intensity writes back to user_model; medium/lower do not."""
    db = _tmp_db()
    store = ReflectionStore(db_path=db)
    llm = FakeLLM({
        "failure_modes": [], "success_patterns": [],
        "suggested_strategy": "Prefer file_ops over bash find.",
    })

    from src.memory.user_model import UserModel
    from src.utils.config import get_config

    cfg_db = _tmp_db()
    # Patch the memory_sqlite_path so UserModel doesn't write to the real DB
    cfg = get_config()
    original_path = cfg._settings.get("memory", {}).get("sqlite_path")
    cfg._settings.setdefault("memory", {})["sqlite_path"] = cfg_db
    try:
        um = UserModel()
        reflector_med = TaskReflector(
            store=store, user_model=um, intensity=INTENSITY_MEDIUM,
            llm_client=llm, model="m",
        )
        reflector_med.reflect(task_id="t_med", session_id="s",
                             task="t", outcome="failure", history=[])
        pref = um.get_preference("task_strategy::t_med")
        assert pref is None, f"medium intensity should NOT write back, got {pref!r}"

        reflector_high = TaskReflector(
            store=store, user_model=um, intensity=INTENSITY_HIGH,
            llm_client=llm, model="m",
        )
        reflector_high.reflect(task_id="t_high", session_id="s",
                              task="t", outcome="failure", history=[])
        pref = um.get_preference("task_strategy::t_high")
        assert pref is not None, "high intensity MUST write back"
        assert "file_ops" in pref
    finally:
        if original_path is None:
            cfg._settings["memory"].pop("sqlite_path", None)
        else:
            cfg._settings["memory"]["sqlite_path"] = original_path


def test_list_recent_session_filter():
    """list_recent must respect session_id filter."""
    db = _tmp_db()
    store = ReflectionStore(db_path=db)
    reflector = TaskReflector(store=store, intensity=INTENSITY_MEDIUM)

    reflector.reflect(task_id="a1", session_id="s1", task="x",
                     outcome="success", history=[])
    reflector.reflect(task_id="a2", session_id="s1", task="y",
                     outcome="failure", history=[])
    reflector.reflect(task_id="b1", session_id="s2", task="z",
                     outcome="success", history=[])

    s1_items = store.list_recent(session_id="s1")
    s2_items = store.list_recent(session_id="s2")
    assert len(s1_items) == 2
    assert len(s2_items) == 1
    assert {r["task_id"] for r in s1_items} == {"a1", "a2"}
    assert s2_items[0]["task_id"] == "b1"


def test_forced_skips_intensity_check():
    """forced=True must bypass intensity gating (for manual /reflect)."""
    db = _tmp_db()
    store = ReflectionStore(db_path=db)
    reflector = TaskReflector(store=store, intensity=INTENSITY_OFF)
    ref = reflector.reflect(task_id="t1", session_id="s",
                            task="manual", outcome="success",
                            history=[], forced=True)
    assert ref is not None
    assert store.get_stats()["total"] == 1


def test_task_reflection_dataclass_roundtrip():
    """TaskReflection.to_dict must serialize all fields."""
    ref = TaskReflection(
        task_id="x", outcome="failure",
        failure_modes=["a", "b"], success_patterns=["c"],
        suggested_strategy="do X",
        step_count=5, tools_used=["click", "type_text"],
        error_count=2, generated_at=__import__("datetime").datetime.now(),
    )
    d = ref.to_dict()
    assert d["task_id"] == "x"
    assert d["failure_modes"] == ["a", "b"]
    assert d["suggested_strategy"] == "do X"
    assert d["error_count"] == 2


if __name__ == "__main__":
    """Minimal test runner — no pytest dependency."""
    import inspect
    import traceback

    tests = [
        (name, fn) for name, fn in globals().items()
        if name.startswith("test_") and callable(fn)
    ]
    passed = failed = 0
    for name, fn in tests:
        try:
            fn()
            passed += 1
            print(f"  PASS  {name}")
        except Exception:
            failed += 1
            print(f"  FAIL  {name}")
            traceback.print_exc()
    print(f"\n{passed} passed, {failed} failed (total {len(tests)})")
    sys.exit(0 if failed == 0 else 1)
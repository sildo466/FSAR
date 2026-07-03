"""Tests for StrategyInjector + DecisionLog (Phase 5.2 + 5.3)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.memory.decision_log import DecisionLog
from src.memory.user_model import UserModel
from src.memory.reflection import ReflectionStore
from src.core.strategy_injector import (
    StrategyInjector,
    INTENSITY_OFF, INTENSITY_LOW, INTENSITY_MEDIUM, INTENSITY_HIGH,
)


def _tmp_db():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    return f.name


def _patch_config_db(db_path: str):
    """Point the global Config at a temp DB so the singleton picks it up."""
    from src.utils.config import get_config
    cfg = get_config()
    cfg._settings.setdefault("memory", {})["sqlite_path"] = db_path
    cfg._settings["memory"]["reflection_intensity"] = "medium"
    return cfg


def test_intensity_off_returns_empty():
    """off intensity must produce no block (no signal even if data exists)."""
    db = _tmp_db()
    _patch_config_db(db)
    try:
        dl = DecisionLog()
        um = UserModel()
        # Seed data
        for i in range(5):
            dl.record(task_id="t1", session_id="s1", step_no=i+1,
                     chosen_tool="file_ops", args_summary="read",
                     latency_ms=10, success=True)
        um.set_preference("editor", "vscode")
        inj = StrategyInjector(decision_log=dl, user_model=um, intensity=INTENSITY_OFF)
        block = inj.build_block()
        assert block == "", f"off intensity must yield empty block, got: {block!r}"
    finally:
        _cleanup(db)


def test_intensity_medium_surfaces_tool_stats():
    """medium intensity surfaces tool_stats hints (low success rate tool)."""
    db = _tmp_db()
    _patch_config_db(db)
    try:
        dl = DecisionLog()
        # 5 calls: 1 success, 4 failures → 20% success
        for i in range(5):
            dl.record(task_id="t1", session_id="s1", step_no=i+1,
                     chosen_tool="run_command", args_summary="x",
                     latency_ms=100, success=(i == 0),
                     error_class="timeout" if i > 0 else "")
        inj = StrategyInjector(decision_log=dl, user_model=UserModel(),
                               intensity=INTENSITY_MEDIUM, min_uses=3,
                               success_rate_threshold=70.0)
        block = inj.build_block()
        assert "run_command" in block, f"expected run_command in block: {block!r}"
        assert "20%" in block or "success" in block.lower()
        assert "timeout" in block
    finally:
        _cleanup(db)


def test_intensity_high_includes_task_strategies():
    """high intensity includes task-reflection suggested_strategy lines."""
    db = _tmp_db()
    _patch_config_db(db)
    try:
        dl = DecisionLog()
        um = UserModel()
        store = ReflectionStore()
        from src.memory.reflection import TaskReflection
        from datetime import datetime
        ref = TaskReflection(
            task_id="t1", outcome="failure",
            failure_modes=["screen race"], success_patterns=[],
            suggested_strategy="Add 200ms sleep before screen capture.",
            step_count=5, tools_used=["click"], error_count=2,
            generated_at=datetime.now(),
        )
        store.save(ref, session_id="s1")
        inj = StrategyInjector(decision_log=dl, user_model=um,
                               intensity=INTENSITY_HIGH)
        block = inj.build_block(recent_strategies=["Add 200ms sleep before screen capture."])
        assert "Learned task strategies" in block
        assert "200ms sleep" in block
    finally:
        _cleanup(db)


def test_intensity_low_omits_tool_stats_but_keeps_prefs():
    """low intensity: prefs surface but tool_stats do not."""
    db = _tmp_db()
    _patch_config_db(db)
    try:
        dl = DecisionLog()
        um = UserModel()
        for i in range(5):
            dl.record(task_id="t1", session_id="s1", step_no=i+1,
                     chosen_tool="web_fetch", args_summary="x",
                     latency_ms=100, success=False, error_class="timeout")
        um.set_preference("language", "Chinese")
        inj = StrategyInjector(decision_log=dl, user_model=um, intensity=INTENSITY_LOW)
        block = inj.build_block()
        assert "language" in block, "low intensity should still surface prefs"
        assert "web_fetch" not in block, "low intensity should NOT surface tool_stats"
    finally:
        _cleanup(db)


def test_min_uses_threshold():
    """Tools with < min_uses must NOT generate avoidance hints."""
    db = _tmp_db()
    _patch_config_db(db)
    try:
        dl = DecisionLog()
        # Only 2 calls (below default min_uses=3)
        for i in range(2):
            dl.record(task_id="t1", session_id="s1", step_no=i+1,
                     chosen_tool="rare_tool", args_summary="x",
                     latency_ms=10, success=False, error_class="unknown")
        inj = StrategyInjector(decision_log=dl, user_model=UserModel(),
                               intensity=INTENSITY_MEDIUM, min_uses=5)
        block = inj.build_block()
        assert "rare_tool" not in block
    finally:
        _cleanup(db)


def test_pref_sources_filter():
    """Only 'explicit', 'reflection', 'task_reflection', 'inferred' sources surface."""
    db = _tmp_db()
    _patch_config_db(db)
    try:
        um = UserModel()
        um.set_preference("good_pref", "value1", source="explicit")
        um.set_preference("bad_pref", "value2", source="system")
        um.set_preference("hidden_pref", "value3", source="deleted")
        um.set_preference("_internal", "value4", source="explicit")
        inj = StrategyInjector(decision_log=DecisionLog(), user_model=um,
                               intensity=INTENSITY_LOW)
        block = inj.build_block()
        assert "good_pref" in block
        assert "bad_pref" not in block
        assert "hidden_pref" not in block
        assert "_internal" not in block
    finally:
        _cleanup(db)


def test_no_data_returns_empty_or_minimal():
    """Empty DB → either empty block or just prefs (no tool_stats line)."""
    db = _tmp_db()
    _patch_config_db(db)
    try:
        inj = StrategyInjector(decision_log=DecisionLog(), user_model=UserModel(),
                               intensity=INTENSITY_MEDIUM)
        block = inj.build_block()
        assert block == ""
    finally:
        _cleanup(db)


def test_strategy_injector_accepts_intensity_changes():
    """set_intensity must validate + update gating."""
    db = _tmp_db()
    _patch_config_db(db)
    try:
        inj = StrategyInjector(intensity=INTENSITY_OFF)
        assert inj.intensity == INTENSITY_OFF
        inj.set_intensity(INTENSITY_HIGH)
        assert inj.intensity == INTENSITY_HIGH
        try:
            inj.set_intensity("nonsense")
        except ValueError:
            return
        raise AssertionError("expected ValueError for invalid intensity")
    finally:
        _cleanup(db)


def _cleanup(db_path: str):
    """Reset config + best-effort delete temp db."""
    from src.utils.config import get_config
    cfg = get_config()
    cfg._settings.get("memory", {}).pop("sqlite_path", None)
    try:
        Path(db_path).unlink(missing_ok=True)
    except Exception:
        pass


if __name__ == "__main__":
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
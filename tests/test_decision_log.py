"""Tests for DecisionLog + @track_decision decorator (Phase 5.2)."""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.memory.decision_log import (
    DecisionLog, DecisionRecord,
    set_task_context, clear_task_context,
)
from src.utils.decorators import track_decision


def _tmp_db():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    return f.name


def _patch_config_db(db_path: str):
    """No-op kept for signature compatibility — DecisionLog now requires
    explicit db_path= when FsarConfig.memory_sqlite_path is unavailable."""
    return None


class FakeTool:
    """Mimics a Tool subclass instance for decorator testing."""
    name = "fake_tool"
    risk_level = "SAFE"

    def __init__(self):
        self.calls = 0

    @track_decision
    async def execute(self, *, x: int = 0, **kwargs) -> str:
        self.calls += 1
        if x < 0:
            raise ValueError(f"x must be >= 0, got {x}")
        return f"ok x={x}"


def test_decision_log_schema():
    """decision_log + tool_stats view must exist after init."""
    db = _tmp_db()
    _patch_config_db(db)
    try:
        log = DecisionLog(db_path=db)
        with log._connect() as conn:
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
            ).fetchall()]
        assert "decision_log" in tables
        assert "tool_stats" in tables
    finally:
        _cleanup(db)


def test_record_and_query():
    db = _tmp_db()
    _patch_config_db(db)
    try:
        log = DecisionLog(db_path=db)
        rid = log.record(task_id="t1", session_id="s1", step_no=1,
                        chosen_tool="file_ops", alternatives=["bash"],
                        args_summary="read x.txt", latency_ms=42,
                        success=True)
        rows = log.get_for_task("t1")
        assert len(rows) == 1
        assert rows[0].chosen_tool == "file_ops"
        assert rows[0].latency_ms == 42
        assert rows[0].success is True
        assert rid == rows[0].id
    finally:
        _cleanup(db)


def test_get_stats_aggregates():
    """tool_stats view must produce correct aggregates."""
    db = _tmp_db()
    _patch_config_db(db)
    try:
        log = DecisionLog(db_path=db)
        for i in range(4):
            log.record(task_id=f"t{i}", session_id="s", step_no=1,
                      chosen_tool="web_search", args_summary="q",
                      latency_ms=100, success=(i < 3))
        log.record(task_id="tx", session_id="s", step_no=1,
                  chosen_tool="web_search", args_summary="q",
                  latency_ms=500, success=False, error_class="timeout")
        stats = log.get_stats(min_uses=3)
        assert len(stats) == 1
        s = stats[0]
        assert s["tool_name"] == "web_search"
        assert s["total_uses"] == 5
        assert s["successes"] == 3
        assert s["failures"] == 2
        assert abs(s["success_rate_pct"] - 60.0) < 0.5
    finally:
        _cleanup(db)


def test_top_failure_modes():
    db = _tmp_db()
    _patch_config_db(db)
    try:
        log = DecisionLog(db_path=db)
        for i in range(3):
            log.record(task_id=f"t{i}", session_id="s", step_no=1,
                      chosen_tool="run_command", args_summary="x",
                      latency_ms=10, success=False, error_class="timeout")
        log.record(task_id="tx", session_id="s", step_no=1,
                  chosen_tool="run_command", args_summary="x",
                  latency_ms=10, success=False, error_class="permission_denied")
        modes = log.get_top_failure_modes("run_command", limit=2)
        assert modes[0] == "timeout"
        assert "permission_denied" in modes
    finally:
        _cleanup(db)


def test_decorator_records_calls():
    """@track_decision must record each invoke into decision_log."""
    db = _tmp_db()
    _patch_config_db(db)
    import src.utils.decorators as dec
    from src.memory.decision_log import DecisionLog as _DL
    dec._decision_log_singleton = _DL(db_path=db)
    try:
        log = DecisionLog(db_path=db)
        set_task_context(task_id="task_a", session_id="sess_1")

        tool = FakeTool()

        async def run():
            return [
                await tool.execute(x=1),
                await tool.execute(x=2),
                await tool.execute(x=-1),
            ]

        try:
            asyncio.run(run())
            raised = False
        except ValueError:
            raised = True
        clear_task_context()

        assert raised, "expected ValueError from third call"

        rows = log.get_for_task("task_a")
        assert len(rows) == 3, f"expected 3 rows, got {len(rows)}"
        assert rows[0].success is True
        assert rows[1].success is True
        assert rows[2].success is False
        assert rows[2].error_class == "bad_input"
    finally:
        _cleanup(db)


def test_decorator_no_context_no_write():
    """Calls without set_task_context must not write rows."""
    db = _tmp_db()
    _patch_config_db(db)
    try:
        log = DecisionLog(db_path=db)
        tool = FakeTool()

        async def run():
            return [await tool.execute(x=1)]

        asyncio.run(run())
        # No set_task_context → no rows should be written
        assert log.get_total() == 0
    finally:
        _cleanup(db)


def test_decorator_handles_tool_method_binding():
    """The decorator must pull tool name from bound instance.name."""
    db = _tmp_db()
    _patch_config_db(db)
    import src.utils.decorators as dec
    from src.memory.decision_log import DecisionLog as _DL
    dec._decision_log_singleton = _DL(db_path=db)
    try:
        log = DecisionLog(db_path=db)
        set_task_context(task_id="bind_test", session_id="s")
        tool = FakeTool()
        asyncio.run(tool.execute(x=1))
        clear_task_context()
        rows = log.get_for_task("bind_test")
        assert len(rows) == 1
        assert rows[0].chosen_tool == "fake_tool"
    finally:
        _cleanup(db)


def test_record_accepts_token_columns():
    db = _tmp_db()
    _patch_config_db(db)
    try:
        log = DecisionLog(db_path=db)
        rid = log.record(
            task_id="tk1", session_id="s1", step_no=1,
            chosen_tool="llm_call", args_summary="q",
            latency_ms=100, success=True,
            prompt_tokens=1200, completion_tokens=350, cached_tokens=900,
        )
        rows = log.get_for_task("tk1")
        assert len(rows) == 1
        r = rows[0]
        assert r.prompt_tokens == 1200
        assert r.completion_tokens == 350
        assert r.cached_tokens == 900
        assert rid == r.id
    finally:
        _cleanup(db)


def test_decision_log_schema_has_token_columns():
    db = _tmp_db()
    _patch_config_db(db)
    try:
        log = DecisionLog(db_path=db)
        with log._connect() as conn:
            cols = {row[1] for row in conn.execute("PRAGMA table_info(decision_log)").fetchall()}
        assert "prompt_tokens" in cols
        assert "completion_tokens" in cols
        assert "cached_tokens" in cols
    finally:
        _cleanup(db)


def test_get_token_totals():
    db = _tmp_db()
    _patch_config_db(db)
    try:
        log = DecisionLog(db_path=db)
        log.record(task_id="a", session_id="s", step_no=1, chosen_tool="llm",
                   prompt_tokens=100, completion_tokens=50, cached_tokens=0)
        log.record(task_id="b", session_id="s", step_no=1, chosen_tool="llm",
                   prompt_tokens=200, completion_tokens=80, cached_tokens=120)
        totals = log.get_token_totals()
        assert totals["prompt_tokens"] == 300
        assert totals["completion_tokens"] == 130
        assert totals["cached_tokens"] == 120
    finally:
        _cleanup(db)


def _cleanup(db_path: str):
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
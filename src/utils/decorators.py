"""FSAR decorators — cross-cutting instrumentation for tools.

@track_decision wraps a Tool.execute() so every invocation is automatically
logged into decision_log (decision_log table) without touching tool code.

Usage:
    from src.utils.decorators import track_decision

    @track_decision
    async def execute(self, **kwargs) -> str:
        ...

The decorator reads task context (set via set_task_context) and records:
- task_id, session_id, step_no (auto-incremented per call)
- chosen_tool = function.__self__.name (from Tool instance)
- args_summary = repr of kwargs (truncated to 500 chars)
- latency_ms, success flag, error_class
"""

from __future__ import annotations

import functools
import inspect
import json
import time
from typing import Any, Callable

from src.utils.logger import logger


_decision_log_singleton = None


def get_decision_log():
    """Lazy-load DecisionLog singleton (avoids circular import at module load)."""
    global _decision_log_singleton
    if _decision_log_singleton is None:
        from src.memory.decision_log import DecisionLog
        _decision_log_singleton = DecisionLog()
    return _decision_log_singleton


def _summarize_args(args: tuple, kwargs: dict) -> str:
    """Compact string representation of call args (truncate large values)."""
    parts: list[str] = []
    if args:
        parts.append(repr(args))
    if kwargs:
        rendered = {}
        for k, v in kwargs.items():
            try:
                s = repr(v)
                if len(s) > 80:
                    s = s[:77] + "..."
                rendered[k] = s
            except Exception:
                rendered[k] = "<unrepr>"
        parts.append(json.dumps(rendered, ensure_ascii=False))
    return " ".join(parts)[:500]


def _extract_alternatives(func: Callable) -> list[str]:
    """Read `alternatives` kwarg if the caller passed it (LLM tool selection
    context). Empty list otherwise.
    """
    try:
        sig = inspect.signature(func)
        bound = func.__wrapped__ if hasattr(func, "__wrapped__") else func
        # Caller may stash alternatives as a kwarg; we look at most recent frame
        # in real stack via wrapper — simpler: check kwargs passed in.
    except Exception:
        pass
    return []


def _extract_tokens(result: Any) -> dict[str, int]:
    """Pull prompt/completion/cached tokens from a function return value.

    Accepts either a dict-style response with `usage` key, or an SDK object
    that exposes `.usage` as a dict. Returns zeroed dict when unavailable.
    """
    out = {"prompt_tokens": 0, "completion_tokens": 0, "cached_tokens": 0}
    try:
        usage = None
        if isinstance(result, dict):
            usage = result.get("usage")
        else:
            usage = getattr(result, "usage", None)
        if not usage:
            return out
        ud = usage if isinstance(usage, dict) else {
            "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
            "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
            "cached_tokens": getattr(usage, "cached_tokens", 0) or 0,
        }
        out["prompt_tokens"] = int(ud.get("prompt_tokens") or 0)
        out["completion_tokens"] = int(ud.get("completion_tokens") or 0)
        out["cached_tokens"] = int(
            ud.get("cached_tokens")
            or ud.get("cache_read_input_tokens")
            or 0
        )
    except Exception:
        pass
    return out


def track_decision(func: Callable) -> Callable:
    """Decorator: record each invocation into decision_log.

    Reads task context via decision_log.get_task_context(). If task_id is
    empty, logs at DEBUG and skips writing (no context = ad-hoc call).

    Sets _fsar_tracked=True on the returned wrapper so ToolRegistry.register
    can detect pre-decorated tools and skip re-wrapping.
    """
    is_coro = inspect.iscoroutinefunction(func)

    if is_coro:

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            from src.memory.decision_log import (
                _classify_error,
                get_task_context,
            )
            ctx = get_task_context()
            task_id = ctx.get("task_id", "")
            session_id = ctx.get("session_id", "")
            ctx["step_no"] = ctx.get("step_no", 0) + 1
            step_no = ctx["step_no"]

            tool_name = _tool_name(args, func)

            t0 = time.perf_counter()
            success = True
            error_class = ""
            tokens: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "cached_tokens": 0}
            try:
                result = await func(*args, **kwargs)
                tokens = _extract_tokens(result)
                return result
            except BaseException as e:
                success = False
                error_class = _classify_error(e)
                raise
            finally:
                latency_ms = int((time.perf_counter() - t0) * 1000)
                if task_id:
                    try:
                        get_decision_log().record(
                            task_id=task_id,
                            session_id=session_id,
                            step_no=step_no,
                            chosen_tool=tool_name,
                            alternatives=kwargs.get("__alternatives__", []) or [],
                            args_summary=_summarize_args(args, kwargs),
                            latency_ms=latency_ms,
                            success=success,
                            error_class=error_class,
                            **tokens,
                        )
                    except Exception as db_err:
                        logger.debug(f"decision_log write skipped: {db_err}")

        async_wrapper._fsar_tracked = True  # type: ignore[attr-defined]
        return async_wrapper

    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        from src.memory.decision_log import _classify_error, get_task_context
        ctx = get_task_context()
        task_id = ctx.get("task_id", "")
        session_id = ctx.get("session_id", "")
        ctx["step_no"] = ctx.get("step_no", 0) + 1
        step_no = ctx["step_no"]

        tool_name = _tool_name(args, func)

        t0 = time.perf_counter()
        success = True
        error_class = ""
        tokens: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "cached_tokens": 0}
        try:
            result = func(*args, **kwargs)
            tokens = _extract_tokens(result)
            return result
        except BaseException as e:
            success = False
            error_class = _classify_error(e)
            raise
        finally:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            if task_id:
                try:
                    get_decision_log().record(
                        task_id=task_id,
                        session_id=session_id,
                        step_no=step_no,
                        chosen_tool=tool_name,
                        alternatives=kwargs.get("__alternatives__", []) or [],
                        args_summary=_summarize_args(args, kwargs),
                        latency_ms=latency_ms,
                        success=success,
                        error_class=error_class,
                        **tokens,
                    )
                except Exception as db_err:
                    logger.debug(f"decision_log write skipped: {db_err}")

    sync_wrapper._fsar_tracked = True  # type: ignore[attr-defined]
    return sync_wrapper


def _tool_name(args: tuple, func: Callable) -> str:
    """Pull tool name from bound instance (first arg = self)."""
    if args and hasattr(args[0], "name"):
        try:
            return str(args[0].name)
        except Exception:
            pass
    return getattr(func, "__qualname__", func.__name__)
"""SchedulerService — APScheduler lifecycle + trigger dispatch.

P1 behavior: _on_trigger writes an 'ok' job_runs row with a P1 stub result
and releases the claim. No real executor runs yet (P2). This lets us verify
the trigger + claim + runs pipeline end-to-end before adding execution logic.

The service emits core.event_bus events on every state change so the WebUI
can listen (P4 wires the WS subscriber).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import TYPE_CHECKING

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.events import EVENT_JOB_MISSED, JobExecutionEvent

from src.core.event_bus import get_event_bus, Event, EventType
from src.scheduler.seed import seed_defaults, SYSTEM_HANDLERS
from src.scheduler.triggers import build_trigger
from src.scheduler.types import JobKind, RunStatus, ScheduleKind

if TYPE_CHECKING:
    from src.scheduler.store import JobStore
    from src.scheduler.types import ScheduledJob


logger = logging.getLogger(__name__)


class SchedulerService:
    def __init__(
        self,
        store: "JobStore",
        *,
        health_interval_seconds: int = 60,
        executor=None,
        delivery=None,
    ):
        self._store = store
        self._sched = AsyncIOScheduler()
        self._bus = get_event_bus()
        self._health_interval = health_interval_seconds
        self._health_task: asyncio.Task | None = None
        self._registered: set[int] = set()
        self._in_flight: set[asyncio.Task] = set()
        self._executor = executor
        self._delivery = delivery

    async def start(self) -> None:
        self._store.ensure_tables()
        seed_defaults(self._store)
        self._sched.add_listener(self._on_apscheduler_missed, EVENT_JOB_MISSED)
        self._sched.start()
        self.reload_all()
        self._health_task = asyncio.create_task(self._health_loop())

    async def stop(self) -> None:
        if self._health_task:
            self._health_task.cancel()
            try:
                await self._health_task
            except (asyncio.CancelledError, Exception):
                pass
            self._health_task = None
        if self._in_flight:
            current_task = asyncio.current_task()
            await asyncio.gather(
                *(task for task in self._in_flight if task is not current_task),
                return_exceptions=True,
            )
            self._in_flight.clear()
        if self._sched.running:
            self._sched.shutdown(wait=False)
        self._registered.clear()

    def reload_all(self) -> None:
        for job in list(self._sched.get_jobs()):
            self._sched.remove_job(job.id)
        self._registered.clear()
        for sj in self._store.list_jobs(enabled_only=True):
            self._register_one(sj)

    def reload_job(self, job_id: int) -> None:
        if job_id in self._registered:
            try:
                self._sched.remove_job(f"job-{job_id}")
            except Exception:
                pass
            self._registered.discard(job_id)
        sj = self._store.get_job(job_id)
        if sj is not None and sj.enabled:
            self._register_one(sj)

    def _register_one(self, sj: "ScheduledJob") -> None:
        try:
            trigger = build_trigger(sj)
        except Exception as e:
            logger.warning(f"job {sj.id} ({sj.name}): trigger build failed: {e}")
            return
        if trigger is None and sj.schedule_kind != ScheduleKind.STARTUP:
            return
        try:
            if sj.schedule_kind == ScheduleKind.STARTUP:
                from apscheduler.triggers.date import DateTrigger
                startup_trigger = DateTrigger(
                    run_date=datetime.now(timezone.utc) + timedelta(seconds=5)
                )
                self._sched.add_job(
                    self._on_trigger,
                    trigger=startup_trigger,
                    args=[sj.id],
                    id=f"job-{sj.id}",
                    replace_existing=True,
                    max_instances=1,
                    coalesce=True,
                )
            else:
                self._sched.add_job(
                    self._on_trigger,
                    trigger=trigger,
                    args=[sj.id],
                    id=f"job-{sj.id}",
                    replace_existing=True,
                    max_instances=1,
                    coalesce=True,
                    misfire_grace_time=60,
                )
            self._registered.add(sj.id)
        except Exception as e:
            logger.warning(f"job {sj.id} ({sj.name}): register failed: {e}")

    async def _on_trigger(self, job_id: int) -> None:
        current_task = asyncio.current_task()
        if current_task is not None:
            self._in_flight = {
                task for task in self._in_flight if not task.done()
            }
            self._in_flight.add(current_task)

        now = datetime.now(timezone.utc)
        if not self._store.claim_job(job_id, now):
            await self._write_skipped(job_id, reason="claim_lost")
            return

        claim_released = False
        try:
            sj = self._store.get_job(job_id)
            if sj is None or not sj.enabled:
                self._store.release_job(job_id, status=RunStatus.SKIPPED,
                                        error="disabled")
                claim_released = True
                return

            run_id = self._store.start_run(job_id, expected_at=now)
            await self._bus.emit(Event(
                type=EventType.SCHEDULER_JOB_STARTED,
                data={"job_id": job_id, "name": sj.name, "run_id": run_id,
                      "expected_at": now.isoformat()},
                source="scheduler",
            ))

            try:
                if sj.job_kind == JobKind.SYSTEM:
                    handler = SYSTEM_HANDLERS.get(sj.name)
                    if handler is None:
                        raise RuntimeError(f"no handler for {sj.name}")
                    await handler({})
                    result_text = (
                        f"[system] {sj.name} fired at {now.isoformat()}"
                    )
                elif sj.job_kind == JobKind.AGENT:
                    if self._executor is None:
                        raise RuntimeError("agent executor not configured")
                    result_text = await self._executor.run(sj)
                else:
                    raise RuntimeError(f"unknown job_kind: {sj.job_kind}")
                self._store.finish_run(run_id, status=RunStatus.OK,
                                       result_text=result_text[:8000])
                finished_run = self._store.list_runs(job_id=job_id, limit=1)[0]
                duration_ms = finished_run.duration_ms
                self._store.release_job(job_id, status=RunStatus.OK, error="",
                                        last_run_at=now)
                claim_released = True
                if self._delivery is not None:
                    try:
                        await self._delivery.deliver(run_id, sj, result_text)
                    except Exception as e:
                        logger.warning(f"delivery failed for run {run_id}: {e}")
                await self._bus.emit(Event(
                    type=EventType.SCHEDULER_JOB_COMPLETED,
                    data={"job_id": job_id, "run_id": run_id, "status": "ok",
                          "duration_ms": duration_ms,
                          "result_preview": result_text[:200]},
                    source="scheduler",
                ))
            except asyncio.CancelledError:
                self._store.finish_run(run_id, status=RunStatus.SKIPPED,
                                       error="cancelled", error_class="cancelled")
                self._store.release_job(job_id, status=RunStatus.SKIPPED,
                                        error="cancelled")
                claim_released = True
                await self._bus.emit(Event(
                    type=EventType.SCHEDULER_JOB_SKIPPED,
                    data={"job_id": job_id, "run_id": run_id, "reason": "cancelled"},
                    source="scheduler",
                ))
                raise
            except Exception as e:
                logger.exception(f"job {sj.id} ({sj.name}) failed")
                self._store.finish_run(run_id, status=RunStatus.ERROR,
                                       error=str(e), error_class="handler_error")
                sj_after = self._store.get_job(job_id)
                new_consec = (sj_after.consecutive_errors if sj_after else 0) + 1
                self._store.release_job(job_id, status=RunStatus.ERROR,
                                        error=str(e)[:500],
                                        consecutive_errors=new_consec,
                                        last_run_at=now)
                claim_released = True
                if new_consec >= 3:
                    self._store.update_job(job_id, {"enabled": False})
                    self.reload_job(job_id)
                    # Spec §9.5: SCHEDULER_JOB_DISABLED not defined yet, emit as FAILED with disable signal
                    await self._bus.emit(Event(
                        type=EventType.SCHEDULER_JOB_FAILED,
                        data={"job_id": job_id, "reason": "consecutive_errors>=3",
                              "disabled": True},
                        source="scheduler",
                    ))
                await self._bus.emit(Event(
                    type=EventType.SCHEDULER_JOB_FAILED,
                    data={"job_id": job_id, "run_id": run_id,
                          "error_class": "handler_error", "error": str(e)[:500]},
                    source="scheduler",
                ))
        finally:
            if not claim_released:
                try:
                    self._store.release_job(job_id, status=RunStatus.ERROR,
                                            error="unexpected_failure")
                except Exception:
                    pass

    async def _on_misfire(self, job_id: int, expected_at: datetime) -> None:
        run_id = self._store.start_run(job_id, expected_at=expected_at)
        self._store.finish_run(run_id, status=RunStatus.MISSED,
                               error_class="misfire")
        sj = self._store.get_job(job_id)
        if sj is not None and sj.running_at is None:
            self._store.update_job(job_id, {
                "last_status": RunStatus.MISSED,
                "last_error": "misfire",
            })
        await self._bus.emit(Event(
            type=EventType.SCHEDULER_JOB_MISSED,
            data={"job_id": job_id, "expected_at": expected_at.isoformat()},
            source="scheduler",
        ))

    async def _health_tick(self) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        for sj in self._store.list_jobs():
            if sj.running_at and sj.running_at < cutoff:
                logger.warning(f"recovering stale lock on job {sj.id} ({sj.name})")
                self._store.release_job(sj.id, status=RunStatus.ERROR,
                                        error="stale_lock_recovered")

    async def _health_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._health_interval)
                try:
                    await self._health_tick()
                except Exception as e:
                    logger.exception(f"health tick failed: {e}")
        except asyncio.CancelledError:
            return

    async def _write_skipped(self, job_id: int, *, reason: str) -> None:
        run_id = self._store.start_run(job_id, expected_at=datetime.now(timezone.utc))
        self._store.finish_run(run_id, status=RunStatus.SKIPPED,
                               error=reason, error_class=reason)
        await self._bus.emit(Event(
            type=EventType.SCHEDULER_JOB_SKIPPED,
            data={"job_id": job_id, "reason": reason},
            source="scheduler",
        ))

    def _on_apscheduler_missed(self, event: JobExecutionEvent) -> None:
        job_id = self._extract_job_id(event.job_id)
        if job_id is None:
            return
        scheduled_time = getattr(event, "scheduled_run_time", None) or datetime.now(timezone.utc)
        asyncio.get_event_loop().create_task(
            self._on_misfire(job_id, scheduled_time)
        )

    @staticmethod
    def _extract_job_id(apsched_job_id: str | None) -> int | None:
        if not apsched_job_id or not apsched_job_id.startswith("job-"):
            return None
        try:
            return int(apsched_job_id[4:])
        except ValueError:
            return None

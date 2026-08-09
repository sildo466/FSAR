import asyncio
import os
import tempfile
from datetime import datetime, timezone, timedelta

import pytest

from src.scheduler.store import JobStore
from src.scheduler.seed import seed_defaults
from src.scheduler.service import SchedulerService
from src.scheduler.types import RunStatus, ScheduledJob, ScheduleKind, JobKind, DeliveryMode


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = JobStore(db_path=path)
    s.ensure_tables()
    yield s
    os.unlink(path)


@pytest.fixture
def service(store):
    return SchedulerService(store=store)


@pytest.mark.asyncio
async def test_start_seeds_if_empty(service, store):
    assert len(store.list_jobs()) == 0
    await service.start()
    try:
        assert len(store.list_jobs()) == 6
    finally:
        await service.stop()


@pytest.mark.asyncio
async def test_start_preserves_existing(service, store):
    seed_defaults(store)
    before = {j.name for j in store.list_jobs()}
    await service.start()
    try:
        after = {j.name for j in store.list_jobs()}
        assert before == after
    finally:
        await service.stop()


@pytest.mark.asyncio
async def test_stop_awaits_in_flight_trigger(service, store):
    seed_defaults(store)
    await service.start()
    try:
        job = store.get_job_by_name("exp_mark_stale")
        task = asyncio.create_task(service._on_trigger(job.id))
        await asyncio.sleep(0.01)
        assert len(service._in_flight) == 1
        await task
    finally:
        await service.stop()
    assert len(service._in_flight) == 0


@pytest.mark.asyncio
async def test_on_trigger_writes_run_and_releases(service, store):
    seed_defaults(store)
    await service.start()
    try:
        job = store.get_job_by_name("exp_mark_stale")
        await service._on_trigger(job.id)
        runs = store.list_runs(job_id=job.id)
        assert len(runs) == 1
        assert runs[0].status == RunStatus.OK
        assert "[system]" in runs[0].result_text or "[agent]" in runs[0].result_text
        got = store.get_job(job.id)
        assert got.running_at is None
        assert got.last_status == RunStatus.OK
    finally:
        await service.stop()


@pytest.mark.asyncio
async def test_on_trigger_skips_disabled(service, store):
    seed_defaults(store)
    job = store.get_job_by_name("idle_reflect")
    store.update_job(job.id, {"enabled": False})
    await service.start()
    try:
        await service._on_trigger(job.id)
        runs = store.list_runs(job_id=job.id)
        assert len(runs) == 1
        assert runs[0].status == RunStatus.SKIPPED
    finally:
        await service.stop()


@pytest.mark.asyncio
async def test_on_misfire_writes_missed_run(service, store):
    seed_defaults(store)
    await service.start()
    try:
        job = store.get_job_by_name("audit_rotate")
        expected = datetime.now(timezone.utc) - timedelta(hours=1)
        await service._on_misfire(job.id, expected)
        runs = store.list_runs(job_id=job.id, status=RunStatus.MISSED)
        assert len(runs) == 1
    finally:
        await service.stop()


@pytest.mark.asyncio
async def test_health_tick_releases_stale_lock(service, store):
    seed_defaults(store)
    job = store.get_job_by_name("idle_reflect")
    long_ago = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    store.update_job(job.id, {"running_at": long_ago})
    await service.start()
    try:
        await service._health_tick()
        got = store.get_job(job.id)
        assert got.running_at is None
    finally:
        await service.stop()


@pytest.mark.asyncio
async def test_startup_job_registers_one_shot(service, store):
    now = datetime.now(timezone.utc)
    job = ScheduledJob(
        id=0,
        name="startup_one_shot",
        description="Startup one-shot for test",
        enabled=True,
        schedule_kind=ScheduleKind.STARTUP,
        schedule_expr="",
        timezone="",
        job_kind=JobKind.SYSTEM,
        prompt="",
        tools_allow="",
        model_override="",
        timeout_seconds=300,
        delivery_mode=DeliveryMode.DB_ONLY,
        delivery_target="",
        running_at=None,
        last_run_at=None,
        last_status=None,
        last_error="",
        consecutive_errors=0,
        created_at=now,
        updated_at=now,
    )
    job_id = store.create_job(job)
    await service.start()
    try:
        apsched_job = service._sched.get_job(f"job-{job_id}")
        assert apsched_job is not None
    finally:
        await service.stop()


@pytest.mark.asyncio
async def test_health_tick_recovers_disabled_stale_lock(service, store):
    seed_defaults(store)
    job = store.get_job_by_name("idle_reflect")
    store.update_job(job.id, {"enabled": False})
    long_ago = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    store.update_job(job.id, {"running_at": long_ago})
    await service.start()
    try:
        await service._health_tick()
        got = store.get_job(job.id)
        assert got.running_at is None
    finally:
        await service.stop()


@pytest.mark.asyncio
async def test_auto_disable_after_three_errors(service, store):
    seed_defaults(store)
    await service.start()
    try:
        job = store.get_job_by_name("exp_mark_stale")
        from src.scheduler import seed as seed_mod
        original = seed_mod.SYSTEM_HANDLERS.get(job.name)

        async def fail_handler(ctx):
            raise RuntimeError("simulated failure")

        seed_mod.SYSTEM_HANDLERS[job.name] = fail_handler
        try:
            for _ in range(3):
                await service._on_trigger(job.id)
            got = store.get_job(job.id)
            assert got.enabled is False
            assert got.consecutive_errors == 3
        finally:
            seed_mod.SYSTEM_HANDLERS[job.name] = original
    finally:
        await service.stop()

import os
import tempfile

import pytest

from src.scheduler.store import JobStore
from src.scheduler.seed import (
    SYSTEM_HANDLERS, DEFAULT_SEED_JOBS, seed_defaults,
)


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = JobStore(db_path=path)
    s.ensure_tables()
    yield s
    os.unlink(path)


def test_system_handlers_has_five_entries():
    assert len(SYSTEM_HANDLERS) == 5
    expected = {
        "idle_reflect", "exp_mark_stale", "exp_mark_archived",
        "tts_cache_sweep", "audit_rotate",
    }
    assert set(SYSTEM_HANDLERS.keys()) == expected


def test_default_seed_jobs_has_five():
    assert len(DEFAULT_SEED_JOBS) == 5
    names = {j.name for j in DEFAULT_SEED_JOBS}
    assert names == set(SYSTEM_HANDLERS.keys())


def test_seed_defaults_first_call_inserts_all(store):
    inserted = seed_defaults(store)
    assert inserted == 5
    jobs = store.list_jobs()
    assert len(jobs) == 5


def test_seed_defaults_idempotent(store):
    first = seed_defaults(store)
    second = seed_defaults(store)
    assert first == 5
    assert second == 0
    assert len(store.list_jobs()) == 5


def test_seed_preserves_user_disabled_state(store):
    seed_defaults(store)
    job = store.get_job_by_name("idle_reflect")
    assert job is not None
    store.update_job(job.id, {"enabled": False})
    seed_defaults(store)
    job2 = store.get_job_by_name("idle_reflect")
    assert job2.enabled is False


def test_seed_jobs_have_valid_schedules():
    from src.scheduler.triggers import build_trigger
    for j in DEFAULT_SEED_JOBS:
        if j.schedule_kind.value == "startup":
            continue
        trigger = build_trigger(j)
        assert trigger is not None, f"bad schedule on {j.name}"

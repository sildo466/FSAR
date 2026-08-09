import os
import tempfile
from datetime import datetime, timezone, timedelta

import pytest

from src.scheduler.types import (
    ScheduleKind, JobKind, DeliveryMode, RunStatus, ScheduledJob,
)
from src.scheduler.store import JobStore


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = JobStore(db_path=path)
    s.ensure_tables()
    yield s
    os.unlink(path)


def _make_job(**overrides) -> ScheduledJob:
    now = datetime.now(timezone.utc)
    defaults = dict(
        id=0, name="t1", description="", enabled=True,
        schedule_kind=ScheduleKind.CRON, schedule_expr="0 9 * * *", timezone="",
        job_kind=JobKind.SYSTEM, prompt="", tools_allow="",
        model_override="", timeout_seconds=60,
        delivery_mode=DeliveryMode.DB_ONLY, delivery_target="",
        running_at=None, last_run_at=None, last_status=None, last_error="",
        consecutive_errors=0,
        created_at=now, updated_at=now,
    )
    defaults.update(overrides)
    return ScheduledJob(**defaults)


def test_create_and_get(store):
    job = _make_job(name="alpha")
    jid = store.create_job(job)
    assert jid > 0
    got = store.get_job(jid)
    assert got is not None
    assert got.name == "alpha"


def test_unique_name(store):
    store.create_job(_make_job(name="dup"))
    with pytest.raises(Exception):
        store.create_job(_make_job(name="dup"))


def test_list_and_filter_enabled(store):
    store.create_job(_make_job(name="on", enabled=True))
    store.create_job(_make_job(name="off", enabled=False))
    all_jobs = store.list_jobs()
    assert len(all_jobs) == 2
    on_only = store.list_jobs(enabled_only=True)
    assert {j.name for j in on_only} == {"on"}


def test_update_and_delete_cascade_runs(store):
    jid = store.create_job(_make_job(name="x"))
    rid = store.start_run(jid, expected_at=datetime.now(timezone.utc))
    assert store.delete_job(jid) is True
    assert store.list_runs(job_id=jid) == []


def test_claim_first_wins_second_loses(store):
    jid = store.create_job(_make_job(name="c"))
    now = datetime.now(timezone.utc)
    assert store.claim_job(jid, now) is True
    assert store.claim_job(jid, now) is False


def test_claim_does_not_reset_consecutive_errors(store):
    jid = store.create_job(_make_job(name="p"))
    now = datetime.now(timezone.utc)
    store.update_job(jid, {"consecutive_errors": 2})
    assert store.claim_job(jid, now) is True
    got = store.get_job(jid)
    assert got.consecutive_errors == 2


def test_claim_recovers_stale_lock_after_one_hour(store):
    jid = store.create_job(_make_job(name="s"))
    long_ago = datetime.now(timezone.utc) - timedelta(hours=2)
    assert store.claim_job(jid, long_ago) is True
    now = datetime.now(timezone.utc)
    assert store.claim_job(jid, now) is True


def test_release_clears_running_and_records_status(store):
    jid = store.create_job(_make_job(name="r"))
    now = datetime.now(timezone.utc)
    store.claim_job(jid, now)
    store.release_job(jid, status=RunStatus.OK, error="")
    got = store.get_job(jid)
    assert got.running_at is None
    assert got.last_status == RunStatus.OK
    assert got.consecutive_errors == 0


def test_release_increments_consecutive_errors_on_failure(store):
    jid = store.create_job(_make_job(name="f"))
    now = datetime.now(timezone.utc)
    store.claim_job(jid, now)
    store.release_job(jid, status=RunStatus.ERROR, error="boom",
                      consecutive_errors=1)
    got = store.get_job(jid)
    assert got.consecutive_errors == 1
    assert got.last_error == "boom"


def test_start_and_finish_run(store):
    jid = store.create_job(_make_job(name="rf"))
    now = datetime.now(timezone.utc)
    rid = store.start_run(jid, expected_at=now)
    store.finish_run(rid, status=RunStatus.OK,
                     result_text="hello", delivery_status="ok")
    runs = store.list_runs(job_id=jid)
    assert len(runs) == 1
    assert runs[0].result_text == "hello"
    assert runs[0].status == RunStatus.OK
    assert runs[0].delivery_status == "ok"


def test_list_runs_filter_by_status(store):
    jid = store.create_job(_make_job(name="mf"))
    now = datetime.now(timezone.utc)
    rid_ok = store.start_run(jid, expected_at=now)
    store.finish_run(rid_ok, status=RunStatus.OK)
    rid_err = store.start_run(jid, expected_at=now)
    store.finish_run(rid_err, status=RunStatus.ERROR, error="x")
    only_errors = store.list_runs(job_id=jid, status=RunStatus.ERROR)
    assert len(only_errors) == 1
    assert only_errors[0].error == "x"
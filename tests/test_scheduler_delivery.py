"""Tests for JobDelivery — db_only + social target parsing."""
import json
import os
import tempfile
from datetime import datetime, timezone

import pytest

from src.scheduler.delivery import JobDelivery, _parse_target
from src.scheduler.types import (
    DeliveryMode, JobKind, ScheduleKind, ScheduledJob, RunStatus,
)
from src.scheduler.store import JobStore


def _job(delivery_mode: str = "db_only", target: str = "") -> ScheduledJob:
    now = datetime.now(timezone.utc)
    return ScheduledJob(
        id=1, name="t", description="", enabled=True,
        schedule_kind=ScheduleKind.CRON, schedule_expr="0 9 * * *", timezone="",
        job_kind=JobKind.AGENT, prompt="hi", tools_allow="[]",
        model_override="", timeout_seconds=60,
        delivery_mode=DeliveryMode(delivery_mode), delivery_target=target,
        running_at=None, last_run_at=None, last_status=None, last_error="",
        consecutive_errors=0, created_at=now, updated_at=now,
    )


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = JobStore(db_path=path)
    s.ensure_tables()
    jid = s.create_job(_job())
    rid = s.start_run(jid, expected_at=datetime.now(timezone.utc))
    s.finish_run(rid, status=RunStatus.OK, result_text="out")
    yield s, jid, rid
    os.unlink(path)


def test_parse_target_valid():
    assert _parse_target("telegram:chat:123") == ("telegram", "chat", "123")
    assert _parse_target("feishu:user:u_abc") == ("feishu", "user", "u_abc")
    assert _parse_target("wechat:group:g_xyz") == ("wechat", "group", "g_xyz")


def test_parse_target_invalid_platform():
    assert _parse_target("slack:chat:1") == (None, None, None)


def test_parse_target_invalid_kind():
    assert _parse_target("telegram:bot:1") == (None, None, None)


def test_parse_target_malformed():
    assert _parse_target("telegram-chat-1") == (None, None, None)
    assert _parse_target("") == (None, None, None)


def test_db_only_delivery_marks_ok(store):
    s, jid, rid = store
    delivery = JobDelivery(store=s, social_router=None)
    import asyncio
    result = asyncio.run(delivery.deliver(rid, _job("db_only"), "result text"))
    assert result.delivered is True
    assert result.channel == "db"
    runs = s.list_runs(job_id=jid, status=RunStatus.OK)
    assert runs[0].delivery_status == "ok"


def test_social_missing_target_marks_failed(store):
    s, jid, rid = store
    delivery = JobDelivery(store=s, social_router=None)
    import asyncio
    result = asyncio.run(delivery.deliver(rid, _job("social", ""), "result"))
    assert result.delivered is False
    assert "missing" in (result.error or "")
    runs = s.list_runs(job_id=jid, status=RunStatus.OK)
    assert runs[0].delivery_status == "failed"


def test_social_invalid_target_marks_failed(store):
    s, jid, rid = store
    delivery = JobDelivery(store=s, social_router=None)
    import asyncio
    result = asyncio.run(delivery.deliver(rid, _job("social", "garbage"), "result"))
    assert result.delivered is False


def test_social_disabled_platform_marks_failed(store):
    s, jid, rid = store
    delivery = JobDelivery(store=s, social_router=None)  # no router
    import asyncio
    result = asyncio.run(delivery.deliver(rid, _job("social", "telegram:chat:1"), "result"))
    assert result.delivered is False
    assert "router" in (result.error or "")
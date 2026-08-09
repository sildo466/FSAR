from src.scheduler.types import (
    ScheduleKind, JobKind, DeliveryMode, RunStatus,
    ScheduledJob, JobRun,
)

def test_schedule_kind_values():
    assert ScheduleKind.CRON.value == "cron"
    assert ScheduleKind.INTERVAL.value == "interval"
    assert ScheduleKind.AT.value == "at"
    assert ScheduleKind.STARTUP.value == "startup"

def test_job_kind_values():
    assert JobKind.SYSTEM.value == "system"
    assert JobKind.AGENT.value == "agent"

def test_delivery_mode_values():
    assert DeliveryMode.DB_ONLY.value == "db_only"
    assert DeliveryMode.SOCIAL.value == "social"

def test_run_status_values():
    assert RunStatus.OK.value == "ok"
    assert RunStatus.ERROR.value == "error"
    assert RunStatus.SKIPPED.value == "skipped"
    assert RunStatus.MISSED.value == "missed"
    assert RunStatus.RUNNING.value == "running"

def test_scheduled_job_required_fields():
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    job = ScheduledJob(
        id=1, name="test", description="",
        enabled=True,
        schedule_kind=ScheduleKind.CRON, schedule_expr="0 9 * * *", timezone="",
        job_kind=JobKind.AGENT, prompt="hi", tools_allow="[]",
        model_override="", timeout_seconds=60,
        delivery_mode=DeliveryMode.DB_ONLY, delivery_target="",
        running_at=None, last_run_at=None, last_status=None, last_error="",
        consecutive_errors=0,
        created_at=now, updated_at=now,
    )
    assert job.name == "test"
    assert job.enabled is True

"""Scheduler type definitions — enums and ORM row dataclasses.

Mirrors the SQLite schema in migrations/0001_init.sql. Every field on
ScheduledJob and JobRun corresponds to a column.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class ScheduleKind(str, Enum):
    CRON = "cron"
    INTERVAL = "interval"
    AT = "at"
    STARTUP = "startup"


class JobKind(str, Enum):
    SYSTEM = "system"
    AGENT = "agent"


class DeliveryMode(str, Enum):
    DB_ONLY = "db_only"
    SOCIAL = "social"


class RunStatus(str, Enum):
    OK = "ok"
    ERROR = "error"
    SKIPPED = "skipped"
    MISSED = "missed"
    RUNNING = "running"


@dataclass
class ScheduledJob:
    id: int
    name: str
    description: str
    enabled: bool
    schedule_kind: ScheduleKind
    schedule_expr: str
    timezone: str
    job_kind: JobKind
    prompt: str
    tools_allow: str
    model_override: str
    timeout_seconds: int
    delivery_mode: DeliveryMode
    delivery_target: str
    running_at: datetime | None
    last_run_at: datetime | None
    last_status: RunStatus | None
    last_error: str
    consecutive_errors: int
    created_at: datetime
    updated_at: datetime


@dataclass
class JobRun:
    id: int
    job_id: int
    expected_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: int | None
    status: RunStatus
    error: str
    error_class: str
    result_text: str
    delivery_status: str
    delivery_error: str
    created_at: datetime

# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from types import SimpleNamespace

import pytest

import src.utils.llm_factory as lf


class _StatusError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"status {status_code}")
        self.status_code = status_code


class _Create:
    def __init__(self, outcomes: list) -> None:
        self.outcomes = list(outcomes)
        self.calls = 0

    def __call__(self, **kwargs):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _Client:
    def __init__(self, outcomes: list) -> None:
        self.base_url = "https://example.invalid/v1"
        self.create = _Create(outcomes)
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self.create),
        )


class _Cfg:
    llm_cache_retention = "none"
    llm_cache_db_path = ""
    llm_cache_session_id = "test-session"

    def get_llm_config(self, provider_id):
        return {}

    def get_active_provider(self):
        return {}

    def get(self, key, default=None):
        return default


@pytest.fixture(autouse=True)
def _stub_dispatch(monkeypatch):
    monkeypatch.setattr(lf, "get_config", lambda: _Cfg())
    monkeypatch.setattr(
        lf, "apply_provider_cache_markers",
        lambda messages, **kwargs: (messages, {}, {}),
    )
    monkeypatch.setattr(
        lf, "detect_provider_family", lambda model="", base_url="": "openai",
    )


def test_retries_429_then_succeeds(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(lf.time, "sleep", sleeps.append)
    client = _Client([_StatusError(429), _StatusError(429), "ok"])

    result = lf.chat_completion(
        client, model="m", messages=[{"role": "user", "content": "x"}],
        usage_recording=False,
    )

    assert result == "ok"
    assert client.create.calls == 3
    assert sleeps == [1.0, 2.0]


def test_does_not_retry_400(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(lf.time, "sleep", sleeps.append)
    client = _Client([_StatusError(400)])

    with pytest.raises(_StatusError):
        lf.chat_completion(
            client, model="m", messages=[{"role": "user", "content": "x"}],
            usage_recording=False,
        )

    assert client.create.calls == 1
    assert sleeps == []


def test_gives_up_after_three_retries(monkeypatch):
    monkeypatch.setattr(lf.time, "sleep", lambda seconds: None)
    client = _Client([_StatusError(503) for _ in range(4)])

    with pytest.raises(_StatusError):
        lf.chat_completion(
            client, model="m", messages=[{"role": "user", "content": "x"}],
            usage_recording=False,
        )

    assert client.create.calls == 4


def test_responses_fallback_retries_only_once(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(lf.time, "sleep", sleeps.append)
    client = _Client([_StatusError(429) for _ in range(4)] + ["ok"])

    with pytest.raises(_StatusError):
        lf.chat_completion(
            client, model="m", messages=[{"role": "user", "content": "x"}],
            format_override="responses", usage_recording=False,
        )

    assert client.create.calls == 4
    assert sleeps == [1.0, 2.0, 4.0]


def test_anthropic_helper_retries_status_errors(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(lf.time, "sleep", sleeps.append)
    create = _Create([_StatusError(429) for _ in range(4)])
    fake_client = SimpleNamespace(
        messages=SimpleNamespace(create=create),
    )
    monkeypatch.setattr(lf, "get_config", lambda: _Cfg())
    monkeypatch.setattr(lf, "make_anthropic_client", lambda provider_id: fake_client)

    result = lf.chat_completion_anthropic(
        messages=[{"role": "user", "content": "x"}],
        model="m",
        cache_retention="none",
    )

    assert create.calls == 4
    assert sleeps == [1.0, 2.0, 4.0]
    assert result.choices[0].message.content.startswith("(Anthropic call failed")


def test_gemini_helper_retries_status_errors(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(lf.time, "sleep", sleeps.append)
    create = _Create([_StatusError(429) for _ in range(4)])
    fake_client = SimpleNamespace(
        models=SimpleNamespace(generate_content=create),
    )
    monkeypatch.setattr(lf, "get_config", lambda: _Cfg())
    monkeypatch.setattr(lf, "make_gemini_client", lambda provider_id: fake_client)

    result = lf.chat_completion_gemini(
        messages=[{"role": "user", "content": "x"}],
        model="m",
        cache_retention="none",
    )

    assert create.calls == 4
    assert sleeps == [1.0, 2.0, 4.0]
    assert result.choices[0].message.content.startswith("(Gemini call failed")


def test_responses_primary_retries_status_errors(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(lf.time, "sleep", sleeps.append)
    create = _Create([_StatusError(429) for _ in range(4)])
    fake_client = SimpleNamespace(
        base_url="https://example.invalid/v1",
        responses=SimpleNamespace(create=create),
    )
    monkeypatch.setattr(lf, "get_config", lambda: _Cfg())

    result = lf.chat_completion_responses(
        fake_client,
        model="m",
        messages=[{"role": "user", "content": "x"}],
        cache_retention="none",
    )

    assert create.calls == 4
    assert sleeps == [1.0, 2.0, 4.0]
    assert result.choices[0].message.content.startswith("(Responses API call failed")

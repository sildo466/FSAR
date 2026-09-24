# SPDX-License-Identifier: MIT
from __future__ import annotations

import json
import urllib.error

import pytest

from src.providers.judge.client import BatchFailed, JevClient


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_nouls_sends_noul_questions_and_returns_scores(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["body"] = json.loads(req.data.decode())
        captured["ua"] = req.headers.get("User-agent")
        return _Resp({"answers": {"a": {"type": "noul", "noul": 0.9}}})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = JevClient("https://x/v1/systemone", "k")
    assert client.nouls("state text", {"a": "is a useful?"}) == {"a": 0.9}
    assert captured["body"]["questions"]["a"]["type"] == "noul"
    assert captured["ua"]
    assert "urllib" not in captured["ua"].lower()


def test_nouls_splits_calls_over_twenty_questions(monkeypatch):
    calls = []

    def fake_urlopen(req, timeout=None):
        body = json.loads(req.data.decode())
        calls.append(len(body["questions"]))
        return _Resp({"answers": {k: {"type": "noul", "noul": 0.5} for k in body["questions"]}})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = JevClient("https://x/v1/systemone", "k")
    out = client.nouls("s", {f"q{i}": "i" for i in range(45)})
    assert calls == [20, 20, 5]
    assert len(out) == 45


def test_nouls_raises_batch_failed_after_retries(monkeypatch):
    def boom(req, timeout=None):
        raise urllib.error.HTTPError("u", 503, "unavailable", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", boom)
    monkeypatch.setattr("time.sleep", lambda *_: None)
    client = JevClient("https://x/v1/systemone", "k")
    with pytest.raises(BatchFailed):
        client.nouls("s", {"a": "i"})


def test_nouls_does_not_retry_on_non_retryable_status(monkeypatch):
    calls = []

    def boom(req, timeout=None):
        calls.append(1)
        raise urllib.error.HTTPError("u", 400, "bad request", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", boom)
    client = JevClient("https://x/v1/systemone", "k")
    with pytest.raises(BatchFailed):
        client.nouls("s", {"a": "i"})
    assert len(calls) == 1

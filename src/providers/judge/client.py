# SPDX-License-Identifier: MIT
"""HTTP client for a JEV (System One) evaluation endpoint.

The endpoint returns typed judgments instead of prose, so it cannot go through
chat_completion. Two server-side constraints shaped this client:

- at most 20 questions per call, so scoring must be batched;
- the front end rejects the default python-urllib User-Agent with HTTP 403
  (Cloudflare error 1010), so a browser-like UA is required.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

MAX_QUESTIONS_PER_CALL = 20
_RETRY_STATUS = {429, 500, 502, 503, 504}
_USER_AGENT = "curl/8.11.1"


class BatchFailed(RuntimeError):
    """One batch exhausted its retries; callers fall back to priority order."""


class JevClient:
    def __init__(self, base_url: str, api_key: str, *, model: str = "",
                 timeout: float = 30.0, attempts: int = 3):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model or "typesafe/jev"
        self.timeout = timeout
        self.attempts = attempts

    def nouls(self, state: str, instructions: dict[str, str]) -> dict[str, float]:
        scores: dict[str, float] = {}
        items = list(instructions.items())
        for start in range(0, len(items), MAX_QUESTIONS_PER_CALL):
            chunk = dict(items[start:start + MAX_QUESTIONS_PER_CALL])
            scores.update(self._one_batch(state, chunk))
        return scores

    def _one_batch(self, state: str, instructions: dict[str, str]) -> dict[str, float]:
        payload = {
            "model": self.model,
            "state": state,
            "questions": {
                k: {"type": "noul", "instructions": v} for k, v in instructions.items()
            },
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        last: Exception | None = None
        for attempt in range(self.attempts):
            req = urllib.request.Request(
                self.base_url,
                data=body,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": _USER_AGENT,
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                return {
                    k: float(v.get("noul", 0.0))
                    for k, v in data.get("answers", {}).items()
                }
            except urllib.error.HTTPError as exc:
                last = exc
                if exc.code not in _RETRY_STATUS:
                    break
                time.sleep(2 * (attempt + 1))
            except Exception as exc:  # transient TLS/connection failure
                last = exc
                time.sleep(2 * (attempt + 1))
        raise BatchFailed(str(last))

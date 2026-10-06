# SPDX-License-Identifier: MIT
from __future__ import annotations

import pytest


class _DisabledGuard:
    """Stands in for the real guard so no test screens content.

    ContentGuard is enabled by default, and ContentScreener reaches the
    configured provider over the network. Every test that writes a preference,
    chunk, pattern or reflection would otherwise trigger a real call.
    """

    enabled = False

    def submit(self, **kwargs) -> None:
        pass


@pytest.fixture(autouse=True)
def _disable_content_guard(monkeypatch):
    from src.security import content_guard

    monkeypatch.setattr(content_guard, "_GUARD", None)
    monkeypatch.setattr(content_guard, "_build_guard", lambda: _DisabledGuard())

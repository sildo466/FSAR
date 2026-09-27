# SPDX-License-Identifier: MIT
"""The connect path must decide and act without blocking on model calls.

Everything here is driven with a temp-backed config, never the module
singleton — the hook saves the config, and that must not touch the real one.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from src.server import ws_server as ws_mod
from src.server.birthday_runner import skins_dir
from src.utils.fsar_config import FsarConfig

# tests/server/conftest.py neutralises the hook so a normal test run cannot
# rewrite the developer's own config; these tests are the exception.
_REAL_PAYLOAD = ws_mod._birthday_connect_payload


@pytest.fixture(autouse=True)
def _use_the_real_hook(monkeypatch):
    monkeypatch.setattr(ws_mod, "_birthday_connect_payload", _REAL_PAYLOAD)


def _temp_config(tmp_path: Path, monkeypatch, installed: str,
                 **settings) -> FsarConfig:
    monkeypatch.setenv("FSAR_CONFIG_PATH", str(tmp_path / "fsar.yaml"))
    cfg = FsarConfig()
    cfg.patch("memory.sqlite_path", str(tmp_path / "memory.db"))
    cfg.patch("data.skins_dir", str(tmp_path / "skins"))
    cfg.patch("style.locale", "en")
    cfg.patch("onboarding.completed_at", installed)
    for key, value in settings.items():
        cfg.patch(key, value)
    return cfg


def test_the_letter_pops_once_and_the_skin_lands(tmp_path, monkeypatch):
    cfg = _temp_config(tmp_path, monkeypatch, installed="2026-01-01T09:00:00",
                       **{"user.birthday": "09-26"})
    monkeypatch.setattr(ws_mod, "_birthday_now", lambda: datetime(2026, 9, 26, 9, 0))

    payload = ws_mod._birthday_connect_payload(cfg)

    assert payload["letter"] is not None
    assert "FSAR" in payload["letter"]
    assert payload["skin_id"] == "birthday"
    assert payload["letters"] is True
    assert (skins_dir(cfg) / "birthday" / "skin.json").is_file()
    assert cfg.get("style.skin_id") == "birthday"
    assert cfg.get("user.birthday_letter_shown") == "2026-09-26"

    again = ws_mod._birthday_connect_payload(cfg)
    assert again["letter"] is None
    assert again["skin_id"] == "birthday"
    assert again["letters"] is False


def test_a_few_days_late_still_grants_the_skin_but_not_the_letter(tmp_path, monkeypatch):
    cfg = _temp_config(tmp_path, monkeypatch, installed="2026-01-01T09:00:00",
                       **{"user.birthday": "09-26"})
    monkeypatch.setattr(ws_mod, "_birthday_now", lambda: datetime(2026, 9, 30, 9, 0))

    payload = ws_mod._birthday_connect_payload(cfg)

    assert payload["letter"] is None
    assert payload["skin_id"] is None
    # The skin and the letters are still due: the day was missed, not the gift.
    assert payload["letters"] is True
    assert cfg.get("style.skin_id") != "birthday"
    assert (skins_dir(cfg) / "birthday" / "skin.json").is_file()
    from src.notifications.store import NotificationStore

    store = NotificationStore(tmp_path / "memory.db")
    assert store.list(kind="birthday"), "the header row still lands"


def test_a_birthday_that_predates_the_install_is_left_alone(tmp_path, monkeypatch):
    """Installing on 09-28 with a 09-26 birthday must not produce a greeting for
    a day that had already passed before the user got here."""
    cfg = _temp_config(tmp_path, monkeypatch, installed="2026-09-28T09:00:00",
                       **{"user.birthday": "09-26"})
    monkeypatch.setattr(ws_mod, "_birthday_now", lambda: datetime(2026, 9, 30, 9, 0))

    payload = ws_mod._birthday_connect_payload(cfg)

    assert payload == {"letter": None, "skin_id": None, "letters": False}
    assert not (skins_dir(cfg) / "birthday").exists()
    from src.notifications.store import NotificationStore

    assert NotificationStore(tmp_path / "memory.db").list(kind="birthday") == []


def test_past_the_window_nothing_is_paid(tmp_path, monkeypatch):
    cfg = _temp_config(tmp_path, monkeypatch, installed="2026-01-01T09:00:00",
                       **{"user.birthday": "09-26"})
    monkeypatch.setattr(ws_mod, "_birthday_now", lambda: datetime(2026, 10, 20, 9, 0))

    payload = ws_mod._birthday_connect_payload(cfg)

    assert payload == {"letter": None, "skin_id": None, "letters": False}
    assert not (skins_dir(cfg) / "birthday").exists()


def test_a_december_birthday_read_in_january_late_delivers(tmp_path, monkeypatch):
    """The occurrence is the most recent one, so this is five days late rather
    than eleven months early."""
    cfg = _temp_config(tmp_path, monkeypatch, installed="2025-01-01T09:00:00",
                       **{"user.birthday": "12-31"})
    monkeypatch.setattr(ws_mod, "_birthday_now", lambda: datetime(2027, 1, 5, 9, 0))

    payload = ws_mod._birthday_connect_payload(cfg)

    assert payload["letters"] is True
    assert payload["letter"] is None
    from src.notifications.store import NotificationStore

    refs = [r["ref"] for r in NotificationStore(tmp_path / "memory.db").list(
        kind="birthday")]
    assert refs == ["2026"], "the header belongs to the cycle that just ended"


def test_no_birthday_configured_is_inert(tmp_path, monkeypatch):
    cfg = _temp_config(tmp_path, monkeypatch, installed="2026-01-01T09:00:00")
    monkeypatch.setattr(ws_mod, "_birthday_now", lambda: datetime(2026, 9, 26, 9, 0))

    payload = ws_mod._birthday_connect_payload(cfg)

    assert payload == {"letter": None, "skin_id": None, "letters": False}
    assert not (skins_dir(cfg) / "birthday").exists()


def test_a_failure_inside_the_hook_is_swallowed(tmp_path, monkeypatch):
    """A broken birthday must never stop the app from connecting."""
    cfg = _temp_config(tmp_path, monkeypatch, installed="2026-01-01T09:00:00",
                       **{"user.birthday": "09-26"})
    monkeypatch.setattr(ws_mod, "_birthday_now", lambda: datetime(2026, 9, 26, 9, 0))

    import src.server.handlers.notifications as notif

    def boom(config):
        raise RuntimeError("boom")

    monkeypatch.setattr(notif, "notification_store", boom)

    assert ws_mod._birthday_connect_payload(cfg) == {
        "letter": None, "skin_id": None, "letters": False,
    }

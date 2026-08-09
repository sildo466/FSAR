"""Cross-platform tests for app_control tool."""

from __future__ import annotations

import sys
from pathlib import Path
import asyncio

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.tools.builtin.app_control import (
    POSIX_ALIASES,
    WINDOWS_ALIASES,
    _resolve_target,
)


def test_linux_generic_aliases_select_linux_launchers(monkeypatch):
    """Generic aliases must invoke Linux-compatible launchers on Linux."""
    import src.tools.builtin.app_control as ac

    monkeypatch.setattr(ac.sys, "platform", "linux")

    assert _resolve_target("terminal") == "x-terminal-emulator"
    assert _resolve_target("files") == ("xdg-open", ".")
    assert _resolve_target("chrome") == "google-chrome"


def test_posix_aliases_exclude_windows_only_wechat():
    assert "wechat" not in POSIX_ALIASES
    assert "wechat" in WINDOWS_ALIASES


def test_posix_alias_and_safe_bare_name_are_allowed(monkeypatch):
    import src.tools.builtin.app_control as ac

    monkeypatch.setattr(ac.sys, "platform", "linux")

    assert _resolve_target("firefox") == "firefox"
    assert _resolve_target("custom-tool") == "custom-tool"


def test_posix_paths_and_parent_segments_are_rejected(monkeypatch):
    import src.tools.builtin.app_control as ac

    monkeypatch.setattr(ac.sys, "platform", "linux")

    assert _resolve_target("/usr/bin/firefox") is None
    assert _resolve_target("../firefox") is None


def test_open_url_macos_uses_open(monkeypatch):
    """macOS URLs must be handed to the platform open command."""
    import src.tools.builtin.app_control as ac
    from src.tools.builtin.app_control import AppControlTool

    captured = []

    def fake_popen(cmd, *args, **kwargs):
        captured.append(cmd)

    monkeypatch.setattr(ac.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(ac.sys, "platform", "darwin")

    assert asyncio.run(AppControlTool().execute(target="https://example.com")) == "Opened: https://example.com"
    assert captured == [["open", "https://example.com"]]


def test_open_url_linux_uses_xdg_open(monkeypatch):
    """Linux URLs must be handed to xdg-open, not the macOS launcher."""
    import src.tools.builtin.app_control as ac
    from src.tools.builtin.app_control import AppControlTool

    captured = []

    def fake_popen(cmd, *args, **kwargs):
        captured.append(cmd)

    monkeypatch.setattr(ac.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(ac.sys, "platform", "linux")

    assert asyncio.run(AppControlTool().execute(target="https://example.com")) == "Opened: https://example.com"
    assert captured == [["xdg-open", "https://example.com"]]


def test_start_app_expands_tuple_target_and_appends_args(monkeypatch):
    """Tuple launch targets must become command arguments before extra args."""
    import src.tools.builtin.app_control as ac
    from src.tools.builtin.app_control import AppControlTool

    captured = []

    def fake_popen(cmd, *args, **kwargs):
        captured.append(cmd)

    monkeypatch.setattr(ac.subprocess, "Popen", fake_popen)

    assert asyncio.run(
        AppControlTool()._start_app(("open", "-a", "Terminal"), "--new-window")
    ) == "Started: ('open', '-a', 'Terminal')"
    assert captured == [["open", "-a", "Terminal", "--new-window"]]

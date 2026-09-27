# SPDX-License-Identifier: MIT
"""The LAN listener is derived from the switches, never remembered."""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

import src.server.lan_supervisor as lan_supervisor
from src.server.lan_supervisor import LanSupervisor, should_listen


class _FakeServer:
    """Models uvicorn.Server: it runs until told to stop, so `is_alive()` is a
    meaningful answer rather than a race against a function that returns."""

    instances: list["_FakeServer"] = []

    def __init__(self, config) -> None:
        self.config = config
        self.started = False
        self.should_exit = False
        _FakeServer.instances.append(self)

    def run(self) -> None:
        self.started = True
        while not self.should_exit:
            time.sleep(0.005)


@pytest.fixture(autouse=True)
def _clear():
    _FakeServer.instances.clear()


def _config(*, enabled: bool, port: int = 8766, host: str = "0.0.0.0"):
    return SimpleNamespace(
        lan_enabled=lambda: enabled,
        lan_bind_host=lambda: host,
        lan_port=lambda: port,
        lan_cert_dir=lambda: "",
    )


def _rooms(*flags: bool):
    return SimpleNamespace(
        list=lambda: [
            SimpleNamespace(id=index + 1, lan_enabled=flag)
            for index, flag in enumerate(flags)
        ],
    )


def _supervisor(tmp_path, *, config=None, rooms=None, **kwargs):
    options = {
        "config": config if config is not None else _config(enabled=True),
        "rooms": rooms if rooms is not None else _rooms(True),
        "deps_factory": lambda: SimpleNamespace(),
        "cert_dir": tmp_path,
        "server_factory": _FakeServer,
    }
    options.update(kwargs)
    return LanSupervisor(**options)


def test_should_listen_needs_both_switches() -> None:
    assert should_listen(_config(enabled=True), _rooms(True)) == (True, 1)
    assert should_listen(_config(enabled=True), _rooms(False)) == (False, 0)
    assert should_listen(_config(enabled=False), _rooms(True)) == (False, 1)
    assert should_listen(_config(enabled=True), _rooms()) == (False, 0)


def test_sync_starts_a_listener_when_both_switches_are_on(tmp_path) -> None:
    supervisor = _supervisor(tmp_path)
    status = supervisor.sync()
    assert status["listening"] is True
    assert len(_FakeServer.instances) == 1
    assert _FakeServer.instances[0].config.host == "0.0.0.0"
    assert _FakeServer.instances[0].config.port == 8766
    supervisor.stop()


def test_sync_is_idempotent(tmp_path) -> None:
    supervisor = _supervisor(tmp_path)
    supervisor.sync()
    supervisor.sync()
    supervisor.sync()
    assert len(_FakeServer.instances) == 1
    supervisor.stop()


def test_sync_stops_when_the_process_switch_goes_off(tmp_path) -> None:
    enabled = {"on": True}
    config = SimpleNamespace(
        lan_enabled=lambda: enabled["on"],
        lan_bind_host=lambda: "0.0.0.0",
        lan_port=lambda: 8766,
        lan_cert_dir=lambda: "",
    )
    supervisor = _supervisor(tmp_path, config=config)
    supervisor.sync()
    enabled["on"] = False
    assert supervisor.sync()["listening"] is False
    assert _FakeServer.instances[0].should_exit is True


def test_sync_stops_when_the_last_lan_room_closes(tmp_path) -> None:
    flags = {"on": True}
    rooms = SimpleNamespace(
        list=lambda: [SimpleNamespace(id=1, lan_enabled=flags["on"])],
    )
    supervisor = _supervisor(tmp_path, rooms=rooms)
    supervisor.sync()
    flags["on"] = False
    assert supervisor.sync()["listening"] is False


def test_status_reports_the_fingerprint_and_room_count(tmp_path) -> None:
    supervisor = _supervisor(tmp_path, rooms=_rooms(True, True))
    status = supervisor.sync()
    assert status["lan_rooms"] == 2
    assert status["fingerprint"].count(":") == 31
    supervisor.stop()


def test_the_certificate_covers_the_local_addresses(tmp_path, monkeypatch) -> None:
    seen: dict = {}

    def spy(cert_dir, *, hosts):
        seen["hosts"] = hosts
        return lan_supervisor.ensure_certificates(cert_dir, hosts=hosts)

    monkeypatch.setattr(lan_supervisor, "ensure_certificates", spy)
    monkeypatch.setattr(
        lan_supervisor, "local_ipv4_addresses",
        lambda: ["127.0.0.1", "10.0.0.5"],
    )
    supervisor = _supervisor(tmp_path)
    supervisor.sync()
    assert seen["hosts"] == ["127.0.0.1", "10.0.0.5"]
    supervisor.stop()


def test_no_certificate_is_generated_while_off(tmp_path) -> None:
    supervisor = _supervisor(tmp_path, config=_config(enabled=False))
    supervisor.sync()
    assert list(tmp_path.iterdir()) == []


def test_a_failed_start_is_reported_rather_than_hidden(tmp_path, monkeypatch) -> None:
    def refuse(_config):
        raise OSError("address in use")

    supervisor = _supervisor(tmp_path, server_factory=refuse)
    status = supervisor.sync()
    assert status["listening"] is False
    assert "address in use" in status["error"]


def test_a_later_sync_recovers_after_a_failed_start(tmp_path) -> None:
    calls = {"n": 0}

    def flaky(config):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("address in use")
        return _FakeServer(config)

    supervisor = _supervisor(tmp_path, server_factory=flaky)
    assert supervisor.sync()["listening"] is False
    assert supervisor.sync()["listening"] is True
    assert supervisor.status()["error"] == ""
    supervisor.stop()


def test_stop_is_safe_when_nothing_is_running(tmp_path) -> None:
    supervisor = _supervisor(tmp_path)
    supervisor.stop()
    assert supervisor.status()["listening"] is False


def test_stop_twice_is_safe(tmp_path) -> None:
    supervisor = _supervisor(tmp_path)
    supervisor.sync()
    supervisor.stop()
    supervisor.stop()
    assert supervisor.status()["listening"] is False

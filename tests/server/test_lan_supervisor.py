# SPDX-License-Identifier: MIT
"""The LAN listener is derived from the switches, never remembered."""

from __future__ import annotations

import socket
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

    def run(self, sockets=None) -> None:
        self.started = True
        while not self.should_exit:
            time.sleep(0.005)


@pytest.fixture(autouse=True)
def _clear():
    _FakeServer.instances.clear()


def _free_port() -> int:
    """The listener now binds for real, so tests must not pick 8766 — that is
    the port a running FSAR may already hold."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


def _config(*, enabled: bool, port: int | None = None, host: str = "0.0.0.0"):
    chosen = _free_port() if port is None else port
    return SimpleNamespace(
        lan_enabled=lambda: enabled,
        lan_bind_host=lambda: host,
        lan_port=lambda: chosen,
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
    config = _config(enabled=True)
    supervisor = _supervisor(tmp_path, config=config)
    status = supervisor.sync()
    assert status["listening"] is True
    assert len(_FakeServer.instances) == 1
    assert _FakeServer.instances[0].config.host == "0.0.0.0"
    assert _FakeServer.instances[0].config.port == config.lan_port()
    assert status["port"] == config.lan_port()
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
    port = _free_port()
    config = SimpleNamespace(
        lan_enabled=lambda: enabled["on"],
        lan_bind_host=lambda: "0.0.0.0",
        lan_port=lambda: port,
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


def test_a_taken_port_is_reported_instead_of_hidden(tmp_path) -> None:
    """The failure mode that looked like "the switch does nothing".

    uvicorn binds inside its own thread, catches the OSError there and calls
    sys.exit(1) — so nothing on this side sees it, the supervisor reported a
    clean start, and status() said the listener was merely down with no reason.
    The listener is therefore bound here first, where a conflict is ours to
    report. No fake server: this is the real uvicorn path.
    """
    occupied = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    occupied.bind(("127.0.0.1", 0))
    occupied.listen(1)
    port = occupied.getsockname()[1]
    try:
        supervisor = LanSupervisor(
            config=_config(enabled=True, host="127.0.0.1", port=port),
            rooms=_rooms(True),
            deps_factory=lambda: SimpleNamespace(),
            cert_dir=tmp_path,
        )
        status = supervisor.sync()
        assert status["listening"] is False
        assert status["error"], "a listener that could not start must say why"
        assert str(port) in status["error"]
        supervisor.stop()
    finally:
        occupied.close()


def test_stopping_frees_the_port_again(tmp_path) -> None:
    """The listener socket is bound here, so this side has to release it."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()

    supervisor = _supervisor(
        tmp_path, config=_config(enabled=True, host="127.0.0.1", port=port),
    )
    assert supervisor.sync()["listening"] is True
    supervisor.stop()

    again = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        again.bind(("127.0.0.1", port))
    finally:
        again.close()


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

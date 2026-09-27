# SPDX-License-Identifier: MIT
"""Owns the second uvicorn listener — the one that faces the network.

Listening is derived, never remembered: the process switch AND at least one
room with LAN on. Anything else means the socket does not exist, which is what
"pause the whole LAN" has to mean to be worth anything.

The trigger points (startup, settings, three room writes) are best effort.
sync() is idempotent and a periodic tick in the server lifespan corrects any
drift — a missed trigger would otherwise look like "I turned it on and nothing
happened", which the user cannot diagnose.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable

from src.security.lan_tls import (
    certificate_fingerprint,
    ensure_certificates,
    local_ipv4_addresses,
)

DEFAULT_CERT_DIR = Path.home() / ".fsar" / "security" / "lan"
CONNECTION_LIMIT = 64


def should_listen(config: Any, rooms: Any) -> tuple[bool, int]:
    lan_rooms = [
        room for room in rooms.list() if getattr(room, "lan_enabled", False)
    ]
    return bool(config.lan_enabled() and lan_rooms), len(lan_rooms)


def _default_server_factory(config: Any) -> Any:
    import uvicorn

    return uvicorn.Server(config)


class LanSupervisor:
    def __init__(
        self,
        *,
        config: Any,
        rooms: Any,
        deps_factory: Callable[[], Any],
        server_factory: Callable[[Any], Any] | None = None,
        cert_dir: Path | None = None,
    ) -> None:
        self.config = config
        self.rooms = rooms
        self.deps_factory = deps_factory
        self.server_factory = server_factory or _default_server_factory
        self.cert_dir = Path(cert_dir) if cert_dir else None
        self._server: Any = None
        self._thread: threading.Thread | None = None
        self._fingerprint = ""
        self._error = ""
        self._lock = threading.Lock()

    def _certificates(self):
        directory = self.cert_dir or (
            Path(self.config.lan_cert_dir()) if self.config.lan_cert_dir()
            else DEFAULT_CERT_DIR
        )
        return ensure_certificates(directory, hosts=local_ipv4_addresses())

    def status(self) -> dict[str, Any]:
        _, lan_rooms = should_listen(self.config, self.rooms)
        return {
            "listening": self._thread is not None and self._thread.is_alive(),
            "host": self.config.lan_bind_host(),
            "port": self.config.lan_port(),
            "fingerprint": self._fingerprint,
            "lan_rooms": lan_rooms,
            "error": self._error,
        }

    def sync(self) -> dict[str, Any]:
        with self._lock:
            want, _ = should_listen(self.config, self.rooms)
            running = self._thread is not None and self._thread.is_alive()
            if want and not running:
                self._start()
            elif not want and running:
                self._stop()
            return self.status()

    def _start(self) -> None:
        try:
            import uvicorn

            certificates = self._certificates()
            self._fingerprint = certificate_fingerprint(certificates.cert_path)
            from src.server.room_app import create_room_app

            server_config = uvicorn.Config(
                create_room_app(self.deps_factory()),
                host=self.config.lan_bind_host(),
                port=self.config.lan_port(),
                ssl_certfile=str(certificates.cert_path),
                ssl_keyfile=str(certificates.key_path),
                log_level="info",
                limit_concurrency=CONNECTION_LIMIT,
                timeout_keep_alive=5,
            )
            self._server = self.server_factory(server_config)
            self._thread = threading.Thread(
                target=self._server.run, name="fsar-lan", daemon=True,
            )
            self._thread.start()
            self._error = ""
        except Exception as exc:
            # A failed start must not leave status() claiming a listener.
            self._server = None
            self._thread = None
            self._error = f"{type(exc).__name__}: {exc}"

    def _stop(self) -> None:
        server, thread = self._server, self._thread
        self._server = None
        self._thread = None
        if server is not None:
            server.should_exit = True
        if thread is not None and thread.is_alive():
            thread.join(timeout=5)

    def stop(self) -> None:
        with self._lock:
            self._stop()

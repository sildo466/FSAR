# SPDX-License-Identifier: MIT
"""The LAN listener's configuration surface."""

from __future__ import annotations

import tempfile
from pathlib import Path

import yaml

from src.utils.fsar_config import FsarConfig


def _config(**lan: object) -> FsarConfig:
    tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    path = Path(tmp.name) / "fsar.yaml"
    path.write_text(yaml.safe_dump({"lan": lan}), encoding="utf-8")
    cfg = FsarConfig(path)
    cfg.load()
    return cfg


def test_lan_defaults_to_off() -> None:
    assert _config().lan_enabled() is False


def test_lan_default_host_and_port() -> None:
    cfg = _config()
    assert cfg.lan_bind_host() == "0.0.0.0"
    assert cfg.lan_port() == 8766


def test_lan_values_are_read() -> None:
    cfg = _config(enabled=True, bind_host="192.168.1.20", port=9000)
    assert cfg.lan_enabled() is True
    assert cfg.lan_bind_host() == "192.168.1.20"
    assert cfg.lan_port() == 9000


def test_lan_port_survives_a_string() -> None:
    assert _config(port="9001").lan_port() == 9001


def test_lan_cert_dir_default_is_empty() -> None:
    assert _config().lan_cert_dir() == ""


def test_lan_enabled_reads_yaml_truthiness() -> None:
    assert _config(enabled="true").lan_enabled() is True


def test_a_quoted_false_is_not_taken_as_on() -> None:
    """bool("false") is True, and this switch opens a network listener."""
    assert _config(enabled="false").lan_enabled() is False
    assert _config(enabled="no").lan_enabled() is False
    assert _config(enabled=0).lan_enabled() is False
    assert _config(enabled=1).lan_enabled() is True

# SPDX-License-Identifier: MIT
"""Self-signed material for the LAN listener."""

from __future__ import annotations

import ipaddress
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from cryptography import x509

from src.security.lan_tls import (
    certificate_fingerprint,
    ensure_certificates,
    local_ipv4_addresses,
)


def _sans(cert_path: Path) -> set[str]:
    cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    extension = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
    return {str(getattr(name, "value", name)) for name in extension.value}


def test_creates_both_files(tmp_path: Path) -> None:
    certs = ensure_certificates(tmp_path, hosts=["127.0.0.1", "192.168.1.20"])
    assert certs.key_path.exists()
    assert certs.cert_path.exists()


def test_the_key_is_written_under_the_given_directory(tmp_path: Path) -> None:
    certs = ensure_certificates(tmp_path, hosts=["127.0.0.1"])
    assert certs.key_path.parent == tmp_path
    assert "key" in certs.key_path.name


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX mode bits are advisory on Windows; the file lives under the "
           "user's home, whose ACL is what actually restricts it",
)
def test_the_key_is_not_readable_by_others(tmp_path: Path) -> None:
    certs = ensure_certificates(tmp_path, hosts=["127.0.0.1"])
    mode = certs.key_path.stat().st_mode & 0o777
    assert mode & 0o077 == 0, f"key is too open: {oct(mode)}"


def test_the_certificate_names_every_host(tmp_path: Path) -> None:
    """A client reaching 192.168.1.20 must find that address in the SAN, or a
    strictly verifying client refuses no matter what the fingerprint says."""
    certs = ensure_certificates(tmp_path, hosts=["127.0.0.1", "192.168.1.20"])
    assert _sans(certs.cert_path) == {"127.0.0.1", "192.168.1.20"}


def test_a_hostname_landing_in_the_san_is_a_dns_entry(tmp_path: Path) -> None:
    certs = ensure_certificates(tmp_path, hosts=["fsar.local"])
    assert "fsar.local" in _sans(certs.cert_path)


def test_every_san_entry_parses_as_an_address_or_a_name(tmp_path: Path) -> None:
    certs = ensure_certificates(tmp_path, hosts=["127.0.0.1", "10.0.0.5", "x.local"])
    cert = x509.load_pem_x509_certificate(certs.cert_path.read_bytes())
    extension = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
    for name in extension.value:
        assert isinstance(name, (x509.IPAddress, x509.DNSName))
        if isinstance(name, x509.IPAddress):
            ipaddress.ip_address(str(name.value))


def test_second_call_reuses_the_same_certificate(tmp_path: Path) -> None:
    first = ensure_certificates(tmp_path, hosts=["127.0.0.1"])
    before = certificate_fingerprint(first.cert_path)
    second = ensure_certificates(tmp_path, hosts=["127.0.0.1"])
    assert certificate_fingerprint(second.cert_path) == before


def test_a_subset_of_hosts_does_not_reissue(tmp_path: Path) -> None:
    first = ensure_certificates(tmp_path, hosts=["127.0.0.1", "192.168.1.20"])
    before = certificate_fingerprint(first.cert_path)
    second = ensure_certificates(tmp_path, hosts=["127.0.0.1"])
    assert certificate_fingerprint(second.cert_path) == before


def test_a_new_host_triggers_a_reissue(tmp_path: Path) -> None:
    first = ensure_certificates(tmp_path, hosts=["127.0.0.1"])
    before = certificate_fingerprint(first.cert_path)
    second = ensure_certificates(tmp_path, hosts=["127.0.0.1", "10.0.0.5"])
    assert certificate_fingerprint(second.cert_path) != before


def test_fingerprint_shape(tmp_path: Path) -> None:
    certs = ensure_certificates(tmp_path, hosts=["127.0.0.1"])
    fingerprint = certificate_fingerprint(certs.cert_path)
    assert fingerprint == fingerprint.upper()
    assert len(fingerprint.split(":")) == 32
    assert all(len(part) == 2 for part in fingerprint.split(":"))


def test_the_certificate_is_self_signed(tmp_path: Path) -> None:
    """What makes `-k` necessary: there is no authority behind it."""
    certs = ensure_certificates(tmp_path, hosts=["127.0.0.1"])
    cert = x509.load_pem_x509_certificate(certs.cert_path.read_bytes())
    assert cert.issuer == cert.subject


def test_the_certificate_is_current(tmp_path: Path) -> None:
    certs = ensure_certificates(tmp_path, hosts=["127.0.0.1"])
    cert = x509.load_pem_x509_certificate(certs.cert_path.read_bytes())
    now = datetime.now(timezone.utc)
    assert cert.not_valid_before_utc <= now <= cert.not_valid_after_utc


def test_a_corrupt_certificate_is_replaced(tmp_path: Path) -> None:
    certs = ensure_certificates(tmp_path, hosts=["127.0.0.1"])
    certs.cert_path.write_bytes(b"not a certificate")
    repaired = ensure_certificates(tmp_path, hosts=["127.0.0.1"])
    assert len(certificate_fingerprint(repaired.cert_path).split(":")) == 32


def test_local_addresses_include_loopback() -> None:
    assert "127.0.0.1" in local_ipv4_addresses()


def test_local_addresses_are_sorted_and_unique() -> None:
    addresses = local_ipv4_addresses()
    assert addresses == sorted(set(addresses))
    assert all(ipaddress.ip_address(entry) for entry in addresses)

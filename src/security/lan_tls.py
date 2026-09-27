# SPDX-License-Identifier: MIT
"""Self-signed TLS material for the LAN room listener.

The host addresses go into the SAN list, so moving to another network changes
the certificate and therefore its fingerprint. That is deliberate: a client
that pinned the fingerprint should notice.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

DAYS_VALID = 825
KEY_NAME = "lan_key.pem"
CERT_NAME = "lan_cert.pem"


@dataclass
class LanCertificates:
    key_path: Path
    cert_path: Path


def local_ipv4_addresses() -> list[str]:
    """Every IPv4 this machine answers on, loopback included, sorted."""
    found = {"127.0.0.1"}
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.add(str(info[4][0]))
    except OSError:
        pass
    try:
        # No packet is sent: this only asks the routing table which local
        # address would be used to reach the outside world.
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(("192.168.1.1", 1))
            found.add(str(probe.getsockname()[0]))
        finally:
            probe.close()
    except OSError:
        pass
    return sorted(found)


def certificate_fingerprint(cert_path: Path) -> str:
    cert = x509.load_pem_x509_certificate(Path(cert_path).read_bytes())
    digest = cert.fingerprint(hashes.SHA256())
    return ":".join(f"{byte:02X}" for byte in digest)


def _sans_in_certificate(cert_path: Path) -> set[str] | None:
    """The SANs already on disk, or None when the file is unusable."""
    try:
        cert = x509.load_pem_x509_certificate(Path(cert_path).read_bytes())
        extension = cert.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        )
    except Exception:
        return None
    values: set[str] = set()
    for name in extension.value:
        raw = getattr(name, "value", None)
        if raw is not None:
            values.add(str(raw))
    return values


def _build(hosts: list[str]) -> tuple[bytes, bytes]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "FSAR room API")])

    entries: list[x509.GeneralName] = []
    for host in sorted(set(hosts)):
        try:
            entries.append(x509.IPAddress(ipaddress.ip_address(host)))
        except ValueError:
            entries.append(x509.DNSName(host))

    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=DAYS_VALID))
        .add_extension(x509.SubjectAlternativeName(entries), critical=False)
        # ca=True with path_length=0 so strict clients accept it as a leaf;
        # it cannot sign anything below it, so this is not a CA.
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(key, hashes.SHA256())
    )
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return key_pem, cert.public_bytes(serialization.Encoding.PEM)


def ensure_certificates(cert_dir: Path, *, hosts: list[str]) -> LanCertificates:
    """Create the pair, or re-issue it when the host set has changed."""
    cert_dir = Path(cert_dir)
    cert_dir.mkdir(parents=True, exist_ok=True)
    key_path = cert_dir / KEY_NAME
    cert_path = cert_dir / CERT_NAME

    wanted = {host for host in hosts if host}
    if key_path.exists() and cert_path.exists() and wanted:
        existing = _sans_in_certificate(cert_path)
        if existing is not None and wanted <= existing:
            return LanCertificates(key_path=key_path, cert_path=cert_path)

    key_pem, cert_pem = _build(sorted(wanted) or ["127.0.0.1"])
    key_path.write_bytes(key_pem)
    cert_path.write_bytes(cert_pem)
    try:
        key_path.chmod(0o600)
    except OSError:
        # Windows: POSIX bits are advisory. The file sits under the user's
        # home, and that directory's ACL is what actually restricts it.
        pass
    return LanCertificates(key_path=key_path, cert_path=cert_path)

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from src.skills.atomic import atomic_write_text
from src.skills.keys import KeyStore


MARKER_NAME = "Safe.txt"


def _b64encode(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _b64decode(value: object) -> bytes:
    if not isinstance(value, str):
        raise ValueError("invalid base64 field")
    return base64.b64decode(value, validate=True)


def subject_path_hash(subject_path: Path) -> str:
    normalized = str(subject_path.resolve()).replace("\\", "/")
    if os.name == "nt":
        normalized = normalized.casefold()
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def content_hash(subject_path: Path, *, supplemental: bytes = b"") -> str:
    digest = hashlib.sha256()
    if subject_path.is_file():
        files = [subject_path]
        root = subject_path.parent
    elif subject_path.is_dir():
        files = sorted(
            (
                path
                for path in subject_path.rglob("*")
                if path.is_file() and path.name != MARKER_NAME
            ),
            key=lambda path: path.relative_to(subject_path).as_posix(),
        )
        root = subject_path
    else:
        raise FileNotFoundError(subject_path)

    for path in files:
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        data = path.read_bytes()
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    digest.update(len(supplemental).to_bytes(8, "big"))
    digest.update(supplemental)
    return f"sha256:{digest.hexdigest()}"


def _aad(path_hash: str, source_hash: str, reviewed_at: str) -> bytes:
    return b"\0".join(
        (path_hash.encode("ascii"), source_hash.encode("ascii"), reviewed_at.encode("ascii"))
    )


@dataclass(frozen=True)
class MarkerVerification:
    valid: bool
    reason: str = ""


class SafeMarker:
    def __init__(self, key_store: KeyStore | None = None) -> None:
        self.key_store = key_store or KeyStore()

    def write(
        self,
        subject_path: Path,
        subject: str,
        *,
        reviewer: str,
        supplemental: bytes = b"",
    ) -> Path:
        path_hash = subject_path_hash(subject_path)
        source_hash = content_hash(subject_path, supplemental=supplemental)
        reviewed_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        keys, nonce = self.key_store.next_nonce()
        sealed = AESGCM(keys.key2).encrypt(
            nonce,
            keys.key1,
            _aad(path_hash, source_hash, reviewed_at),
        )
        payload = {
            "version": 1,
            "subject": subject,
            "subject_path_hash": path_hash,
            "content_hash": source_hash,
            "reviewer": reviewer,
            "reviewed_at": reviewed_at,
            "aead": {
                "cipher": "AES-256-GCM",
                "nonce": _b64encode(nonce),
                "ct": _b64encode(sealed[:-16]),
                "tag": _b64encode(sealed[-16:]),
            },
            "Key1": _b64encode(keys.key1),
        }
        marker_path = subject_path / MARKER_NAME if subject_path.is_dir() else subject_path.parent / MARKER_NAME
        atomic_write_text(
            marker_path,
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            mode=0o600,
        )
        return marker_path

    def verify(
        self,
        subject_path: Path,
        subject: str,
        *,
        supplemental: bytes = b"",
    ) -> MarkerVerification:
        marker_path = subject_path / MARKER_NAME if subject_path.is_dir() else subject_path.parent / MARKER_NAME
        if not marker_path.is_file():
            return MarkerVerification(False, "marker_missing")
        try:
            payload = json.loads(marker_path.read_text(encoding="utf-8"))
            if payload.get("version") != 1:
                return MarkerVerification(False, "version")
            if payload.get("subject") != subject:
                return MarkerVerification(False, "subject")
            path_hash = subject_path_hash(subject_path)
            source_hash = content_hash(subject_path, supplemental=supplemental)
            if not hmac.compare_digest(payload.get("subject_path_hash", ""), path_hash):
                return MarkerVerification(False, "path_changed")
            if not hmac.compare_digest(payload.get("content_hash", ""), source_hash):
                return MarkerVerification(False, "content_changed")
            reviewed_at = payload["reviewed_at"]
            aead = payload["aead"]
            if aead.get("cipher") != "AES-256-GCM":
                return MarkerVerification(False, "cipher")
            nonce = _b64decode(aead.get("nonce"))
            ciphertext = _b64decode(aead.get("ct")) + _b64decode(aead.get("tag"))
            marker_key1 = _b64decode(payload.get("Key1"))
            keys = self.key_store.load_or_create()
            plaintext = AESGCM(keys.key2).decrypt(
                nonce,
                ciphertext,
                _aad(path_hash, source_hash, reviewed_at),
            )
            if not hmac.compare_digest(plaintext, marker_key1):
                return MarkerVerification(False, "key_mismatch")
            if not hmac.compare_digest(plaintext, keys.key1):
                return MarkerVerification(False, "key_rotated")
        except (InvalidTag, KeyError, TypeError, ValueError, OSError, json.JSONDecodeError):
            return MarkerVerification(False, "invalid_marker")
        return MarkerVerification(True)

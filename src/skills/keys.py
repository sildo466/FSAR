from __future__ import annotations

import base64
import json
import secrets
import threading
from dataclasses import dataclass
from pathlib import Path

from src.skills.atomic import atomic_write_text
from src.utils.fsar_home import get_fsar_home


_KEY_LOCK = threading.RLock()


def _encode(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _decode(value: object, field: str) -> bytes:
    if not isinstance(value, str):
        raise ValueError(f"invalid {field}")
    try:
        decoded = base64.b64decode(value, validate=True)
    except Exception as error:
        raise ValueError(f"invalid {field}") from error
    if len(decoded) != 32:
        raise ValueError(f"invalid {field} length")
    return decoded


@dataclass(frozen=True)
class SecurityKeys:
    key1: bytes
    key2: bytes
    nonce_counter: int


class KeyStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or get_fsar_home() / "security" / "keys.json"

    def load_or_create(self) -> SecurityKeys:
        with _KEY_LOCK:
            if not self.path.exists():
                keys = SecurityKeys(
                    key1=secrets.token_bytes(32),
                    key2=secrets.token_bytes(32),
                    nonce_counter=0,
                )
                self._write(keys)
                return keys
            return self._read()

    def next_nonce(self) -> tuple[SecurityKeys, bytes]:
        with _KEY_LOCK:
            keys = self.load_or_create()
            counter = keys.nonce_counter + 1
            if counter >= 1 << 96:
                raise OverflowError("security nonce counter exhausted")
            updated = SecurityKeys(keys.key1, keys.key2, counter)
            self._write(updated)
            return updated, counter.to_bytes(12, "big")

    def _read(self) -> SecurityKeys:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as error:
            raise ValueError(f"invalid security key store: {self.path}") from error
        if payload.get("version") != 1:
            raise ValueError("unsupported security key store version")
        counter = payload.get("nonce_counter")
        if not isinstance(counter, int) or counter < 0:
            raise ValueError("invalid nonce_counter")
        return SecurityKeys(
            key1=_decode(payload.get("key1"), "key1"),
            key2=_decode(payload.get("key2"), "key2"),
            nonce_counter=counter,
        )

    def _write(self, keys: SecurityKeys) -> None:
        payload = {
            "version": 1,
            "key1": _encode(keys.key1),
            "key2": _encode(keys.key2),
            "nonce_counter": keys.nonce_counter,
        }
        atomic_write_text(
            self.path,
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            mode=0o600,
        )


def load_security_keys() -> SecurityKeys:
    return KeyStore().load_or_create()


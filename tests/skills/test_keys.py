from __future__ import annotations

import json

import pytest

from src.skills.keys import KeyStore


def test_key_store_generates_persistent_keys_and_unique_nonces(tmp_path):
    store = KeyStore(tmp_path / "security" / "keys.json")

    initial = store.load_or_create()
    updated, first_nonce = store.next_nonce()
    latest, second_nonce = store.next_nonce()

    assert len(initial.key1) == 32
    assert len(initial.key2) == 32
    assert initial.key1 == updated.key1 == latest.key1
    assert initial.key2 == updated.key2 == latest.key2
    assert first_nonce != second_nonce
    assert latest.nonce_counter == 2


def test_key_store_rejects_corrupt_data(tmp_path):
    path = tmp_path / "keys.json"
    path.write_text(json.dumps({"version": 1}), encoding="utf-8")

    with pytest.raises(ValueError, match="nonce_counter"):
        KeyStore(path).load_or_create()

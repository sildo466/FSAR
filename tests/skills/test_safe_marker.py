from __future__ import annotations

import json

from src.skills.keys import KeyStore
from src.skills.safe_marker import SafeMarker


def test_safe_marker_verifies_unchanged_directory(tmp_path):
    skill = tmp_path / "hello"
    skill.mkdir()
    (skill / "SKILL.md").write_text("Hello", encoding="utf-8")
    marker = SafeMarker(KeyStore(tmp_path / "security" / "keys.json"))

    marker.write(skill, "skill:hello", reviewer="test")

    assert marker.verify(skill, "skill:hello").valid


def test_safe_marker_rejects_content_and_marker_tampering(tmp_path):
    skill = tmp_path / "hello"
    skill.mkdir()
    source = skill / "main.py"
    source.write_text("print('hi')", encoding="utf-8")
    marker = SafeMarker(KeyStore(tmp_path / "keys.json"))
    marker_path = marker.write(skill, "skill:hello", reviewer="test")

    source.write_text("print('changed')", encoding="utf-8")
    assert marker.verify(skill, "skill:hello").reason == "content_changed"

    source.write_text("print('hi')", encoding="utf-8")
    payload = json.loads(marker_path.read_text(encoding="utf-8"))
    payload["reviewed_at"] = "2026-01-01T00:00:00Z"
    marker_path.write_text(json.dumps(payload), encoding="utf-8")
    assert marker.verify(skill, "skill:hello").reason == "invalid_marker"


def test_safe_marker_binds_supplemental_data(tmp_path):
    server = tmp_path / "server"
    server.mkdir()
    marker = SafeMarker(KeyStore(tmp_path / "keys.json"))
    marker.write(server, "mcp:test", reviewer="user", supplemental=b"command-a")

    assert marker.verify(server, "mcp:test", supplemental=b"command-a").valid
    assert marker.verify(server, "mcp:test", supplemental=b"command-b").reason == "content_changed"

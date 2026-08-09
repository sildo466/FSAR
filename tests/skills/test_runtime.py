from __future__ import annotations

from src.skills.runtime import build_subprocess_env
from src.utils.fsar_config import FsarConfig


def _config(tmp_path, enabled: bool) -> FsarConfig:
    path = tmp_path / "fsar.yaml"
    path.write_text(
        "security:\n  skills:\n    subprocess_env:\n      enabled: "
        + ("true\n" if enabled else "false\n")
        + "      allow: [PATH, HOME, OPENAI_API_KEY]\n"
        + "      strip_prefixes: [API_KEY, TOKEN, SECRET, AUTH]\n",
        encoding="utf-8",
    )
    return FsarConfig(path)


def test_subprocess_environment_allows_only_safe_names(tmp_path):
    result = build_subprocess_env(
        _config(tmp_path, True),
        source={
            "PATH": "path",
            "HOME": "home",
            "OPENAI_API_KEY": "secret",
            "MCP_SERVERS": "secret",
            "UNRELATED": "value",
        },
    )

    assert result == {"PATH": "path", "HOME": "home"}


def test_disabled_isolation_inherits_parent_environment(tmp_path):
    result = build_subprocess_env(
        _config(tmp_path, False),
        source={"PATH": "path", "CUSTOM": "value", "AUTH_HEADER": "secret"},
    )

    assert result == {"PATH": "path", "CUSTOM": "value", "AUTH_HEADER": "secret"}

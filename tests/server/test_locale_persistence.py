# SPDX-License-Identifier: MIT
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from src.utils.fsar_config import FsarConfig

LOCALES = {"en", "zh-Hans", "zh-Hant", "ja", "de", "fr"}


def _write_config(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body), encoding="utf-8")


def test_default_locale_is_en(tmp_path: Path) -> None:
    cfg = FsarConfig(path=tmp_path / "fsar.yaml")
    assert cfg.style_locale == "en"


def test_existing_locale_is_loaded(tmp_path: Path) -> None:
    path = tmp_path / "fsar.yaml"
    _write_config(path, """
        style:
          locale: zh-Hans
    """)
    cfg = FsarConfig(path=path)
    assert cfg.style_locale == "zh-Hans"


def test_locale_field_in_template() -> None:
    template = Path(__file__).resolve().parents[2] / "config" / "fsar.yaml.template"
    body = template.read_text(encoding="utf-8")
    assert "style:" in body
    style_section = body.split("style:", 1)[1]
    assert "locale:" in style_section
    assert "locale: en" in style_section


def test_style_set_locale_valid_persists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_path = tmp_path / "fsar.yaml"
    _write_config(cfg_path, "style:\n  theme: system\n")
    monkeypatch.setenv("FSAR_CONFIG_PATH", str(cfg_path))
    import src.utils.fsar_config as mod
    mod._default_instance = None
    cfg = mod.get_default_config()

    from src.server.handlers.settings import dispatch
    import asyncio

    seen: list[dict] = []

    class FakeWS:
        async def send_json(self, payload: dict) -> None:
            seen.append(payload)

    msg = {"type": "style.set_locale", "locale": "zh-Hans"}
    handled = asyncio.run(dispatch(FakeWS(), msg, cfg))  # type: ignore[arg-type]
    assert handled is True
    assert cfg.style_locale == "zh-Hans"
    assert any(p.get("type") == "style.changed" for p in seen)
    assert any(p.get("style", {}).get("locale") == "zh-Hans" for p in seen)


def test_style_set_locale_invalid_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_path = tmp_path / "fsar.yaml"
    _write_config(cfg_path, "style:\n  theme: system\n")
    monkeypatch.setenv("FSAR_CONFIG_PATH", str(cfg_path))
    import src.utils.fsar_config as mod
    mod._default_instance = None
    cfg = mod.get_default_config()

    from src.server.handlers.settings import dispatch
    import asyncio

    seen: list[dict] = []

    class FakeWS:
        async def send_json(self, payload: dict) -> None:
            seen.append(payload)

    msg = {"type": "style.set_locale", "locale": "klingon"}
    handled = asyncio.run(dispatch(FakeWS(), msg, cfg))  # type: ignore[arg-type]
    assert handled is True
    assert cfg.style_locale == "en"
    bad = [p for p in seen if p.get("type") == "error" and p.get("code") == "bad_locale"]
    assert len(bad) == 1

# SPDX-License-Identifier: Apache-2.0
"""Integration test: clean start triggers wizard via fsar.yaml auto-creation."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.server.ws_server import ensure_config


def test_first_run_creates_yaml_from_template(tmp_path: Path, monkeypatch):
    """When config/fsar.yaml is missing, ensure_config copies template to it."""
    template = tmp_path / "fsar.yaml.template"
    template.write_text(
        "onboarding:\n  completed: false\n  completed_at: null\n  completed_steps: []\n",
        encoding="utf-8",
    )
    yaml_path = tmp_path / "fsar.yaml"
    assert not yaml_path.exists()

    ensure_config(yaml_path=yaml_path, template_path=template)

    assert yaml_path.exists()
    assert "onboarding" in yaml_path.read_text(encoding="utf-8")
    assert "completed: false" in yaml_path.read_text(encoding="utf-8")


def test_first_run_does_not_overwrite_existing(tmp_path: Path):
    """If fsar.yaml exists, ensure_config is a no-op."""
    template = tmp_path / "fsar.yaml.template"
    template.write_text("onboarding:\n  completed: false\n", encoding="utf-8")
    yaml_path = tmp_path / "fsar.yaml"
    yaml_path.write_text("onboarding:\n  completed: true\n", encoding="utf-8")

    ensure_config(yaml_path=yaml_path, template_path=template)

    assert "completed: true" in yaml_path.read_text(encoding="utf-8")


def test_first_run_missing_template_raises(tmp_path: Path):
    """If template is also missing, raise (cannot bootstrap)."""
    yaml_path = tmp_path / "fsar.yaml"
    template = tmp_path / "fsar.yaml.template"  # not created
    with pytest.raises(FileNotFoundError, match="template"):
        ensure_config(yaml_path=yaml_path, template_path=template)

# SPDX-License-Identifier: MIT
"""The snapshot: an allowlist, no history, and nothing that can be run."""

from __future__ import annotations

import os
import subprocess
import tarfile
from pathlib import Path

import pytest

from src.server.publish_export import (
    ExportError, build_export, collect, matches_allowlist,
)


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("FSAR_HOME", str(tmp_path / "home"))


def _project(tmp_path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "t"], check=True)
    (root / "app.py").write_text("print('hi')\n", encoding="utf-8")
    (root / "README.md").write_text("hello\n", encoding="utf-8")
    (root / ".env").write_text("SECRET=1\n", encoding="utf-8")
    (root / "blob.bin").write_bytes(b"\x00\x01\x02binary")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "init"], check=True)
    return root


def test_an_empty_allowlist_publishes_nothing(tmp_path) -> None:
    with pytest.raises(ExportError):
        collect(_project(tmp_path), [])


def test_only_what_the_allowlist_names_is_taken(tmp_path) -> None:
    root = _project(tmp_path)

    taken = [str(p).replace("\\", "/") for p in collect(root, ["*.py"])]

    assert taken == ["app.py"]


def test_a_dot_file_never_leaves_even_if_allowlisted(tmp_path) -> None:
    root = _project(tmp_path)

    taken = [str(p).replace("\\", "/") for p in collect(root, ["*"])]

    assert ".env" not in taken
    assert "app.py" in taken


def test_dot_git_never_leaves(tmp_path) -> None:
    root = _project(tmp_path)

    result = build_export(root, ["*"], 1)

    with tarfile.open(result.path) as tar:
        names = tar.getnames()
    assert not [n for n in names if n.startswith(".git")]
    assert "app.py" in names


def test_a_binary_is_not_taken(tmp_path) -> None:
    root = _project(tmp_path)

    taken = [str(p).replace("\\", "/") for p in collect(root, ["*"])]

    assert "blob.bin" not in taken


def test_a_symlink_is_not_taken(tmp_path) -> None:
    root = _project(tmp_path)
    try:
        (root / "link.py").symlink_to("app.py")
    except (OSError, NotImplementedError):
        pytest.skip("this platform cannot make a symlink without privileges")

    taken = [str(p).replace("\\", "/") for p in collect(root, ["*"])]

    assert "link.py" not in taken


@pytest.mark.skipif(os.name != "posix", reason="only posix has an execute bit")
def test_an_executable_is_not_taken(tmp_path) -> None:
    root = _project(tmp_path)
    (root / "run.py").write_text("print(1)\n", encoding="utf-8")
    (root / "run.py").chmod(0o755)

    taken = [str(p).replace("\\", "/") for p in collect(root, ["*"])]

    assert "run.py" not in taken


def test_the_package_reports_its_own_size(tmp_path) -> None:
    root = _project(tmp_path)

    result = build_export(root, ["*.py", "*.md"], 3)

    assert result.path.exists()
    assert result.path_count == 2
    assert result.byte_count == result.path.stat().st_size
    assert len(result.digest) == 64


def test_the_allowlist_is_a_glob_over_the_whole_path(tmp_path) -> None:
    assert matches_allowlist("src/app.py", ["src/*.py"]) is True
    assert matches_allowlist("docs/app.py", ["src/*.py"]) is False
    assert matches_allowlist("src\\deep\\app.py", ["src/**"]) is True

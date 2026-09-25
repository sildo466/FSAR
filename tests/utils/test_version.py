# SPDX-License-Identifier: MIT
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.utils.version import (
    app_version,
    base_tag,
    channel_of,
    compare_tags,
    describe_tag,
    parse_tag,
    pyproject_version,
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=T", *args],
        cwd=str(repo),
        check=True,
        capture_output=True,
        text=True,
    )


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "f.txt").write_text("x")
    _git(repo, "add", "f.txt")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


@pytest.mark.parametrize(
    "tag,expected",
    [
        ("v0.5.0", ((0, 5, 0), None)),
        ("v0.6.0-beta1", ((0, 6, 0), ("beta", 1))),
        ("v0.6.0-beta1-31-gad68159", ((0, 6, 0), ("beta", 1))),
        ("v0.2.1.1", ((0, 2, 1, 1), None)),
        ("0.6.0-dirty", ((0, 6, 0), None)),
    ],
)
def test_parse_tag(tag: str, expected):
    assert parse_tag(tag) == expected


@pytest.mark.parametrize("tag", ["", "unknown", "release-candidate", "vX.Y"])
def test_parse_tag_rejects_garbage(tag: str):
    assert parse_tag(tag) is None


@pytest.mark.parametrize(
    "a,b,expected",
    [
        ("v0.5.0", "v0.6.0-beta1", -1),
        ("v0.6.0-beta1", "v0.5.0", 1),
        ("v0.6.0-beta1", "v0.6.0", -1),
        ("v0.6.0", "v0.6.0-beta1", 1),
        ("v0.6.0-beta1", "v0.6.0-beta2", -1),
        ("v0.6.0-beta1", "v0.6.0-beta1-31-gad68159", 0),
        ("v0.5.0", "v0.2.1.1", 1),
        ("v0.5.0", "v0.5.0", 0),
    ],
)
def test_compare_tags(a: str, b: str, expected: int):
    assert compare_tags(a, b) == expected


def test_compare_tags_returns_none_when_unparseable():
    assert compare_tags("unknown", "v0.5.0") is None


@pytest.mark.parametrize(
    "tag,expected",
    [
        ("v0.6.0-beta1", "beta"),
        ("v0.6.0-beta1-31-gad68159", "beta"),
        ("v0.5.0", "stable"),
        ("unknown", "stable"),
    ],
)
def test_channel_of(tag: str, expected: str):
    assert channel_of(tag) == expected


@pytest.mark.parametrize(
    "tag,expected",
    [
        ("v0.6.0-beta1-31-gad68159", "v0.6.0-beta1"),
        ("v0.6.0-beta1-31-gad68159-dirty", "v0.6.0-beta1"),
        ("v0.6.0-beta1-1-gca206f5-dirty", "v0.6.0-beta1"),
        ("v0.5.0", "v0.5.0"),
        ("v0.5.0-dirty", "v0.5.0"),
    ],
)
def test_base_tag(tag: str, expected: str):
    assert base_tag(tag) == expected


def test_describe_tag_reads_the_nearest_tag(tmp_path: Path):
    repo = _init_repo(tmp_path)
    _git(repo, "tag", "v0.6.0-beta1")
    assert describe_tag(repo) == "v0.6.0-beta1"


def test_describe_tag_counts_commits_past_the_tag(tmp_path: Path):
    repo = _init_repo(tmp_path)
    _git(repo, "tag", "v0.6.0-beta1")
    (repo / "f.txt").write_text("y")
    _git(repo, "commit", "-q", "-am", "more")
    assert describe_tag(repo).startswith("v0.6.0-beta1-1-g")


def test_describe_tag_returns_none_outside_a_repo(tmp_path: Path):
    assert describe_tag(tmp_path) is None


def test_pyproject_version_reads_project_version(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "fsar"\nversion = "0.5.0"\n'
    )
    assert pyproject_version(tmp_path) == "v0.5.0"


def test_pyproject_version_returns_none_when_absent(tmp_path: Path):
    assert pyproject_version(tmp_path) is None


def test_app_version_prefers_git(tmp_path: Path):
    repo = _init_repo(tmp_path)
    _git(repo, "tag", "v0.6.0-beta1")
    (repo / "pyproject.toml").write_text('[project]\nversion = "9.9.9"\n')
    payload = app_version(repo)
    assert payload == {
        "tag": "v0.6.0-beta1",
        "base": "v0.6.0-beta1",
        "channel": "beta",
        "exact": True,
        "source": "git",
    }


def test_app_version_falls_back_to_pyproject(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "0.5.0"\n')
    assert app_version(tmp_path) == {
        "tag": "v0.5.0",
        "base": "v0.5.0",
        "channel": "stable",
        "exact": True,
        "source": "pyproject",
    }


def test_app_version_marks_unknown_when_nothing_available(tmp_path: Path):
    payload = app_version(tmp_path)
    assert payload["tag"] == "unknown"
    assert payload["exact"] is False

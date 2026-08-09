from pathlib import Path

from src.sandbox.paths import is_inside, normalize_path, safe_resolve


def test_normalize_removes_invisible_and_at_prefix():
    assert normalize_path(" @\u200bfoo/bar ") == "foo/bar"


def test_normalize_nfkc():
    assert normalize_path("Ａ.txt") == "A.txt"


def test_normalize_expands_home_variable(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert normalize_path("$HOME/secret") == str(tmp_path) + "/secret"


def test_safe_resolve_relative_to_base(tmp_path: Path):
    assert safe_resolve("notes/a.txt", base=tmp_path) == (tmp_path / "notes/a.txt").resolve()


def test_inside_accepts_descendant(tmp_path: Path):
    assert is_inside(tmp_path / "a/b", tmp_path)


def test_inside_rejects_sibling(tmp_path: Path):
    assert not is_inside(tmp_path.parent / "outside", tmp_path)


def test_safe_resolve_follows_symlink_when_supported(tmp_path: Path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        return
    assert safe_resolve(str(link / "secret")) == (outside / "secret").resolve()

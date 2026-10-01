# SPDX-License-Identifier: MIT
"""The shapes a patch may not arrive in."""

from __future__ import annotations

from src.server.patch_text import check_patch

LIMIT = 512 * 1024

_HEADER = "diff --git a/app.py b/app.py\n"
_BODY = "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n"


def _ok(text: str) -> bool:
    return check_patch(text, max_bytes=LIMIT)[0]


def test_an_ordinary_patch_is_accepted() -> None:
    assert _ok(_HEADER + _BODY) is True


def test_an_empty_patch_is_refused() -> None:
    assert _ok("   \n") is False


def test_something_that_is_not_a_diff_is_refused() -> None:
    assert _ok("please apply this, thanks") is False


def test_a_nul_byte_is_refused() -> None:
    assert _ok(_HEADER + "\x00") is False


def test_a_binary_patch_is_refused() -> None:
    assert _ok(_HEADER + "GIT binary patch\nliteral 3\n") is False


def test_a_binary_files_line_is_refused() -> None:
    assert _ok(_HEADER + "Binary files a/x and b/x differ\n") is False


def test_a_mode_change_is_refused() -> None:
    assert _ok(_HEADER + "old mode 100644\nnew mode 100755\n" + _BODY) is False


def test_a_new_symlink_is_refused() -> None:
    assert _ok(
        "diff --git a/link b/link\nnew file mode 120000\n"
        "--- /dev/null\n+++ b/link\n@@ -0,0 +1 @@\n+target\n"
    ) is False


def test_a_new_plain_file_is_accepted() -> None:
    assert _ok(
        "diff --git a/new.py b/new.py\nnew file mode 100644\n"
        "--- /dev/null\n+++ b/new.py\n@@ -0,0 +1 @@\n+x = 1\n"
    ) is True


def test_a_submodule_change_is_refused() -> None:
    assert _ok(_HEADER + "Submodule lib 0000000..1111111:\n") is False


def test_a_patch_over_the_limit_is_refused() -> None:
    assert _ok(_HEADER + _BODY + "x" * LIMIT) is False


def test_a_non_ascii_path_is_not_second_guessed() -> None:
    """git quotes these by default; the shape check must not turn that into a
    refusal or a project with non-ASCII filenames could never contribute."""
    assert _ok(
        'diff --git "a/\\346\\226\\207\\346\\241\\243.md" '
        '"b/\\346\\226\\207\\346\\241\\243.md"\n'
        '--- "a/\\346\\226\\207\\346\\241\\243.md"\n'
        '+++ "b/\\346\\226\\207\\346\\241\\243.md"\n@@ -1 +1 @@\n-a\n+b\n'
    ) is True

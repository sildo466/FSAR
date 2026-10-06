# SPDX-License-Identifier: MIT
"""Reading a patch before writing it.

This layer is shape only. Paths are not parsed here: git owns that format
and quotes non-ASCII paths, so a hand-rolled reader would refuse a project
whose filenames are not ASCII. Where a path may land is decided on the tree
after the patch is applied, and git itself refuses to reach outside the
worktree.

That split also decides what this layer is for: it fails fast on the shapes
that are never a contribution, so the staging is not touched by them at all.
"""

from __future__ import annotations

_BINARY_MARKERS = ("GIT binary patch", "Binary files ")


def check_patch(text: str, *, max_bytes: int) -> tuple[bool, str]:
    if not text.strip():
        return False, "the patch is empty"
    try:
        size = len(text.encode("utf-8"))
    except UnicodeEncodeError:
        return False, "the patch is not valid UTF-8"
    if size > max_bytes:
        return False, f"the patch is larger than {max_bytes} bytes"
    if "\0" in text:
        return False, "the patch carries a NUL byte"
    if "diff --git " not in text:
        return False, "the patch is not a git diff"
    for marker in _BINARY_MARKERS:
        if marker in text:
            return False, "binary patches are not accepted"

    for line in text.splitlines():
        if line.startswith("Submodule "):
            return False, "submodule changes are not accepted"
        if line.startswith("old mode ") or line.startswith("new mode "):
            return False, "the patch changes a file mode"
        if line.startswith("new file mode ") and not line.endswith("100644"):
            return False, "the patch creates something that is not a plain file"
    return True, ""

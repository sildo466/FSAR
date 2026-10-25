# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from src.tools.builtin.edit import EditTool
from src.tools.builtin.file_ops import FileOpsTool


async def test_edit_preserves_lf(tmp_path):
    path = tmp_path / "a.py"
    path.write_bytes(b"one\ntwo\n")
    result = await EditTool().execute(
        file_path=str(path), old_text="two", new_text="three",
        _sandbox_prevalidated=True,
    )
    assert result.startswith("Replaced")
    assert path.read_bytes() == b"one\nthree\n"


async def test_edit_preserves_crlf(tmp_path):
    path = tmp_path / "a.py"
    path.write_bytes(b"one\r\ntwo\r\n")
    result = await EditTool().execute(
        file_path=str(path), old_text="two", new_text="three",
        _sandbox_prevalidated=True,
    )
    assert result.startswith("Replaced")
    assert path.read_bytes() == b"one\r\nthree\r\n"


async def test_file_ops_write_keeps_lf(tmp_path):
    path = tmp_path / "a.txt"
    result = await FileOpsTool().execute(
        operation="write", path=str(path), content="a\nb\n",
        _sandbox_prevalidated=True,
    )
    assert result.startswith("Successfully wrote")
    assert path.read_bytes() == b"a\nb\n"

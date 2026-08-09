from __future__ import annotations

from src.skills.reviewer import Reviewer


def test_reviewer_accepts_plain_markdown_and_python(tmp_path):
    (tmp_path / "SKILL.md").write_text("# Hello\nUse the helper.", encoding="utf-8")
    (tmp_path / "main.py").write_text("print('hello')", encoding="utf-8")

    report = Reviewer().review(tmp_path)

    assert report.verdict == "PASS"
    assert report.files_checked == 2


def test_reviewer_scans_markdown_for_denied_patterns(tmp_path):
    (tmp_path / "SKILL.md").write_text("Run `eval(user_input)`.", encoding="utf-8")

    report = Reviewer().review(tmp_path)

    assert report.verdict == "FAIL"
    assert any(item.code == "dynamic_eval" and item.file == "SKILL.md" for item in report.findings)


def test_reviewer_rejects_shell_true_and_binary_magic(tmp_path):
    (tmp_path / "main.py").write_text(
        'subprocess.run("dir", shell=True)', encoding="utf-8"
    )
    (tmp_path / "payload.txt").write_bytes(b"MZ" + b"\0" * 10)

    report = Reviewer().review(tmp_path)

    assert report.verdict == "FAIL"
    codes = {item.code for item in report.findings}
    assert "shell_subprocess" in codes
    assert "pe_binary" in codes


def test_reviewer_rejects_unlisted_extension(tmp_path):
    (tmp_path / "payload.exe").write_bytes(b"plain text")

    report = Reviewer().review(tmp_path)

    assert report.verdict == "FAIL"
    assert report.findings[0].code == "extension_not_allowed"

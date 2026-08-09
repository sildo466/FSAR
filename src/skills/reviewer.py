from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from src.skills.safe_marker import MARKER_NAME


ALLOWED_EXTENSIONS = {
    ".py", ".pyi", ".md", ".txt", ".json", ".yaml", ".yml", ".toml",
    ".cfg", ".ini", ".sh", ".ps1", ".js", ".ts", ".html", ".css",
}
MAX_FILE_BYTES = 1024 * 1024
MAX_TOTAL_BYTES = 5 * 1024 * 1024
MAX_FILES = 50

MAGIC_BYTES = {
    b"MZ": "pe_binary",
    b"\x7fELF": "elf_binary",
    b"\xfe\xed\xfa": "macho_binary",
    b"PK\x03\x04": "zip_archive",
}

DENY_PATTERNS = {
    "dynamic_eval": re.compile(r"\beval\s*\(", re.IGNORECASE),
    "dynamic_exec": re.compile(r"\bexec\s*\(", re.IGNORECASE),
    "dynamic_compile": re.compile(r"\bcompile\s*\(", re.IGNORECASE),
    "dynamic_import": re.compile(r"__import__\s*\(", re.IGNORECASE),
    "shell_subprocess": re.compile(
        r"subprocess\.[A-Za-z_]+\s*\([^)]*shell\s*=\s*True",
        re.IGNORECASE | re.DOTALL,
    ),
    "os_system": re.compile(r"os\.system\s*\(", re.IGNORECASE),
    "os_popen": re.compile(r"os\.popen\s*\(", re.IGNORECASE),
    "pickle_load": re.compile(r"pickle\.loads?\s*\(", re.IGNORECASE),
    "marshal_load": re.compile(r"marshal\.loads?\s*\(", re.IGNORECASE),
    "encoded_payload": re.compile(
        r"base64\.[A-Za-z_]+\s*\(\s*[A-Za-z0-9+/=]{40,}\s*\)",
        re.IGNORECASE,
    ),
    "raw_socket": re.compile(r"socket\.socket\s*\(", re.IGNORECASE),
    "urllib_request": re.compile(r"urllib\.request", re.IGNORECASE),
    "httpx_request": re.compile(r"httpx\.[A-Za-z_]+\s*\(", re.IGNORECASE),
    "requests_request": re.compile(r"requests\.[A-Za-z_]+\s*\(", re.IGNORECASE),
    "ctypes_call": re.compile(r"ctypes\.[A-Za-z_]+\s*\(", re.IGNORECASE),
    "etc_passwd": re.compile(r"open\s*\([^)]*['\"]\s*/etc/passwd", re.IGNORECASE),
    "proc_read": re.compile(r"open\s*\([^)]*['\"]\s*/proc/", re.IGNORECASE),
}

WARN_PATTERNS = {
    "subprocess_usage": re.compile(r"\bsubprocess\.", re.IGNORECASE),
    "environment_access": re.compile(r"\bos\.environ\b", re.IGNORECASE),
    "filesystem_write": re.compile(r"\b(?:write_text|write_bytes)\s*\(", re.IGNORECASE),
}


@dataclass(frozen=True)
class ReviewFinding:
    level: str
    code: str
    file: str = ""
    line: int | None = None


@dataclass(frozen=True)
class ReviewReport:
    verdict: str
    findings: list[ReviewFinding] = field(default_factory=list)
    files_checked: int = 0
    total_bytes: int = 0


class Reviewer:
    reviewer_id = "fsar-deterministic-review-v1"

    def review(self, skill_path: Path) -> ReviewReport:
        findings: list[ReviewFinding] = []
        if not skill_path.is_dir():
            return ReviewReport("FAIL", [ReviewFinding("FAIL", "not_directory")])

        entries = sorted(
            (path for path in skill_path.rglob("*") if path.name != MARKER_NAME),
            key=lambda path: path.relative_to(skill_path).as_posix(),
        )
        files: list[Path] = []
        root = skill_path.resolve()
        for path in entries:
            relative = path.relative_to(skill_path).as_posix()
            if ".." in Path(relative).parts:
                findings.append(ReviewFinding("FAIL", "path_traversal", relative))
                continue
            if path.is_symlink():
                try:
                    linked = Path(os.readlink(path))
                    direct_target = linked if linked.is_absolute() else path.parent / linked
                    target = path.resolve(strict=True)
                    target.relative_to(root)
                except (OSError, ValueError):
                    findings.append(ReviewFinding("FAIL", "unsafe_symlink", relative))
                    continue
                if direct_target.is_symlink():
                    findings.append(ReviewFinding("FAIL", "symlink_chain", relative))
                    continue
            if path.is_file():
                files.append(path)

        if len(files) > MAX_FILES:
            findings.append(ReviewFinding("FAIL", "too_many_files"))

        total_bytes = 0
        for path in files:
            relative = path.relative_to(skill_path).as_posix()
            extension = path.suffix.lower()
            if extension not in ALLOWED_EXTENSIONS:
                findings.append(ReviewFinding("FAIL", "extension_not_allowed", relative))
            try:
                size = path.stat().st_size
                data = path.read_bytes()
            except OSError:
                findings.append(ReviewFinding("FAIL", "unreadable_file", relative))
                continue
            total_bytes += size
            if size > MAX_FILE_BYTES:
                findings.append(ReviewFinding("FAIL", "file_too_large", relative))
            for signature, code in MAGIC_BYTES.items():
                if data[:8].startswith(signature):
                    findings.append(ReviewFinding("FAIL", code, relative))
                    break
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                findings.append(ReviewFinding("FAIL", "non_utf8_content", relative))
                continue
            findings.extend(self._scan_text(relative, text))

        if total_bytes > MAX_TOTAL_BYTES:
            findings.append(ReviewFinding("FAIL", "directory_too_large"))

        fail_count = sum(item.level == "FAIL" for item in findings)
        warn_count = sum(item.level == "WARN" for item in findings)
        verdict = "FAIL" if fail_count else "WARN" if warn_count >= 3 else "PASS"
        return ReviewReport(verdict, findings, len(files), total_bytes)

    @staticmethod
    def _scan_text(relative: str, text: str) -> list[ReviewFinding]:
        findings: list[ReviewFinding] = []
        for code, pattern in DENY_PATTERNS.items():
            for match in pattern.finditer(text):
                findings.append(
                    ReviewFinding("FAIL", code, relative, text.count("\n", 0, match.start()) + 1)
                )
        for code, pattern in WARN_PATTERNS.items():
            match = pattern.search(text)
            if match:
                findings.append(
                    ReviewFinding("WARN", code, relative, text.count("\n", 0, match.start()) + 1)
                )
        return findings

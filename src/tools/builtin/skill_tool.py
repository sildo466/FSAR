from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from src.skills.gate import gate_skill, mcp_config_bytes, validate_subject_name
from src.skills.llm_review import LLMSkillJudge
from src.skills.reviewer import Reviewer
from src.skills.runtime import run_python_skill
from src.skills.safe_marker import SafeMarker
from src.tools.registry import Tool
from src.security.audit import append_skill_review
from src.utils.fsar_config import FsarConfig
from src.utils.fsar_home import get_fsar_home


_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


class _SkillTool(Tool):
    def __init__(
        self,
        config: FsarConfig,
        *,
        skills_root: Path | None = None,
        marker: SafeMarker | None = None,
    ) -> None:
        self.config = config
        self.skills_root = skills_root or get_fsar_home() / "skills"
        self.marker = marker or SafeMarker()

    def _path(self, name: str) -> Path:
        return self.skills_root / validate_subject_name(name)


class SkillRunTool(_SkillTool):
    @property
    def name(self) -> str:
        return "skill_run"

    @property
    def description(self) -> str:
        return "Run a local FSAR skill after its configured review gate allows execution."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Skill directory name."},
                "args": {"type": "object", "default": {}, "description": "JSON arguments for the skill."},
                "timeout": {"type": "integer", "default": 30, "minimum": 1, "maximum": 120},
            },
            "required": ["name"],
        }

    @property
    def risk_level(self) -> str:
        return "HIGH"

    async def execute(
        self,
        *,
        name: str,
        args: dict[str, Any] | None = None,
        timeout: int = 30,
        **kwargs: Any,
    ) -> str:
        try:
            skill_path = self._path(name)
        except ValueError:
            return "[BLOCKED: invalid skill name]"
        verdict = gate_skill(
            name,
            self.config,
            skills_root=self.skills_root,
            marker=self.marker,
        )
        if not verdict.valid:
            return f"[BLOCKED: skill '{name}' not reviewed ({verdict.reason})]"
        if not skill_path.is_dir():
            return f"[NOT_FOUND] Skill '{name}' does not exist."
        entry = _read_entrypoint(skill_path)
        if entry is None:
            return f"[BLOCKED: skill '{name}' has no Python entrypoint]"
        try:
            result = await run_python_skill(
                entry, args or {}, self.config, timeout=timeout
            )
        except OSError as error:
            return f"[ERROR] Skill '{name}' failed to start: {error}"
        if result.timed_out:
            return f"[BLOCKED: skill '{name}' timed out]"
        if result.returncode:
            return f"[ERROR] Skill '{name}' exited {result.returncode}: {result.stderr or result.stdout}"
        return result.stdout or (
            f"stderr:\n{result.stderr}" if result.stderr else "[OK] Skill completed."
        )


class SkillReviewTool(_SkillTool):
    @property
    def name(self) -> str:
        return "skill_review"

    @property
    def description(self) -> str:
        return "Review a local skill and issue an authenticated Safe.txt marker when approved."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Skill directory name."}},
            "required": ["name"],
        }

    @property
    def risk_level(self) -> str:
        return "HIGH"

    async def execute(self, *, name: str, **kwargs: Any) -> str:
        if name.startswith("mcp:"):
            return await self._review_mcp(name[4:])
        try:
            skill_path = self._path(name)
        except ValueError:
            return "[BLOCKED: invalid skill name]"
        report = Reviewer().review(skill_path)
        findings = [
            {"level": item.level, "code": item.code, "file": item.file, "line": item.line}
            for item in report.findings
        ]
        if report.verdict == "FAIL":
            append_skill_review(
                subject=f"skill:{name}", verdict="FAIL",
                reviewer=Reviewer.reviewer_id, findings=findings,
            )
            return json.dumps({"verdict": "FAIL", "findings": findings}, ensure_ascii=False)
        reviewer_id = Reviewer.reviewer_id
        if self.config.get("security.skills.llm_review.enabled", False):
            try:
                llm_verdict = await LLMSkillJudge(self.config).review(
                    skill_path, report.findings
                )
            except Exception as error:
                append_skill_review(
                    subject=f"skill:{name}", verdict="FAIL", reviewer="llm",
                    findings=[*findings, {"level": "FAIL", "code": "llm_error", "message": str(error)}],
                )
                return json.dumps(
                    {"verdict": "FAIL", "findings": findings, "llm_reason": str(error)},
                    ensure_ascii=False,
                )
            if not llm_verdict.safe:
                append_skill_review(
                    subject=f"skill:{name}", verdict="FAIL", reviewer="llm",
                    findings=[*findings, {"level": "FAIL", "code": "llm_unsafe", "message": llm_verdict.reason}],
                )
                return json.dumps(
                    {
                        "verdict": "FAIL",
                        "findings": findings,
                        "llm_reason": llm_verdict.reason,
                    },
                    ensure_ascii=False,
                )
            reviewer_id += "+llm"
        self.marker.write(
            skill_path,
            f"skill:{name}",
            reviewer=reviewer_id,
        )
        append_skill_review(
            subject=f"skill:{name}", verdict=report.verdict,
            reviewer=reviewer_id, findings=findings,
        )
        return json.dumps(
            {"verdict": report.verdict, "findings": findings, "marker": "Safe.txt"},
            ensure_ascii=False,
        )

    async def _review_mcp(self, name: str) -> str:
        try:
            validate_subject_name(name)
        except ValueError:
            return "[BLOCKED: invalid MCP server name]"
        server = next(
            (item for item in self.config.get_mcp_servers() if item.get("name") == name),
            None,
        )
        if server is None:
            return f"[NOT_FOUND] MCP server '{name}' is not configured."
        server_path = get_fsar_home() / "mcp_servers" / name
        server_path.mkdir(parents=True, exist_ok=True)
        report = Reviewer().review(server_path)
        if report.verdict == "FAIL":
            mcp_findings = [
                {"level": item.level, "code": item.code, "file": item.file, "line": item.line}
                for item in report.findings
            ]
            append_skill_review(
                subject=f"mcp:{name}", verdict="FAIL",
                reviewer=Reviewer.reviewer_id, findings=mcp_findings,
            )
            return json.dumps(
                {
                    "verdict": "FAIL",
                    "findings": mcp_findings,
                },
                ensure_ascii=False,
            )
        self.marker.write(
            server_path,
            f"mcp:{name}",
            reviewer=Reviewer.reviewer_id,
            supplemental=mcp_config_bytes(server),
        )
        append_skill_review(
            subject=f"mcp:{name}", verdict=report.verdict,
            reviewer=Reviewer.reviewer_id, findings=[],
        )
        return json.dumps(
            {"verdict": report.verdict, "subject": f"mcp:{name}", "marker": "Safe.txt"},
            ensure_ascii=False,
        )


class SkillListTool(_SkillTool):
    @property
    def name(self) -> str:
        return "skill_list"

    @property
    def description(self) -> str:
        return "List installed local skills and their review status without exposing skill contents."

    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {}, "required": []}

    @property
    def risk_level(self) -> str:
        return "SAFE"

    async def execute(self, **kwargs: Any) -> str:
        if not self.skills_root.is_dir():
            return "[]"
        rows = []
        for path in sorted(self.skills_root.iterdir(), key=lambda item: item.name.casefold()):
            if not path.is_dir():
                continue
            try:
                verdict = gate_skill(
                    path.name,
                    self.config,
                    skills_root=self.skills_root,
                    marker=self.marker,
                )
            except ValueError:
                continue
            rows.append({"name": path.name, "reviewed": verdict.valid, "reason": verdict.reason})
        return json.dumps(rows, ensure_ascii=False)


def _read_entrypoint(skill_path: Path) -> Path | None:
    metadata_path = skill_path / "SKILL.md"
    entry = "main.py"
    if metadata_path.is_file():
        text = metadata_path.read_text(encoding="utf-8")
        match = _FRONTMATTER.match(text)
        if match:
            metadata = yaml.safe_load(match.group(1)) or {}
            if isinstance(metadata, dict) and isinstance(metadata.get("entry"), str):
                entry = metadata["entry"].strip()
    relative = Path(entry)
    if relative.is_absolute() or ".." in relative.parts or relative.suffix.lower() != ".py":
        return None
    candidate = (skill_path / relative).resolve()
    try:
        candidate.relative_to(skill_path.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None

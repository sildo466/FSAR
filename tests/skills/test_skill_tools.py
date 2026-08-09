from __future__ import annotations

import asyncio
import json

from src.skills.keys import KeyStore
from src.skills.llm_review import LLMReviewVerdict
from src.skills.safe_marker import SafeMarker
from src.tools.builtin.skill_tool import SkillListTool, SkillReviewTool, SkillRunTool
from src.utils.fsar_config import FsarConfig


def _config(tmp_path, *, llm_review: bool = True) -> FsarConfig:
    path = tmp_path / "fsar.yaml"
    path.write_text(
        "security:\n  skills:\n    review_required: true\n    llm_review:\n      enabled: "
        + ("true\n" if llm_review else "false\n"),
        encoding="utf-8",
    )
    return FsarConfig(path)


def test_skill_run_is_blocked_until_reviewed(tmp_path, monkeypatch):
    skills = tmp_path / "skills"
    skill = skills / "hello"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# Hello", encoding="utf-8")
    (skill / "main.py").write_text("print('hi')", encoding="utf-8")
    marker = SafeMarker(KeyStore(tmp_path / "security" / "keys.json"))
    config = _config(tmp_path)
    run = SkillRunTool(config, skills_root=skills, marker=marker)
    review = SkillReviewTool(config, skills_root=skills, marker=marker)

    async def safe_review(*args, **kwargs):
        return LLMReviewVerdict(True)

    monkeypatch.setattr("src.tools.builtin.skill_tool.LLMSkillJudge.review", safe_review)
    monkeypatch.setattr("src.tools.builtin.skill_tool.append_skill_review", lambda **kwargs: None)

    assert "not reviewed" in asyncio.run(run.execute(name="hello"))
    assert json.loads(asyncio.run(review.execute(name="hello")))["verdict"] == "PASS"
    assert asyncio.run(run.execute(name="hello")) == "hi"


def test_review_disabled_bypasses_marker_per_policy(tmp_path):
    skills = tmp_path / "skills"
    skill = skills / "hello"
    skill.mkdir(parents=True)
    (skill / "main.py").write_text("print('hi')", encoding="utf-8")
    config = _config(tmp_path, llm_review=False)

    result = asyncio.run(SkillRunTool(config, skills_root=skills).execute(name="hello"))

    assert result == "hi"


def test_skill_list_does_not_expose_contents(tmp_path):
    skills = tmp_path / "skills"
    skill = skills / "secret"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("DO NOT EXPOSE", encoding="utf-8")

    result = asyncio.run(SkillListTool(_config(tmp_path), skills_root=skills).execute())

    assert "secret" in result
    assert "DO NOT EXPOSE" not in result

"""Tests for the declarative skill registry."""

import pytest
from bot.skills import SKILLS, LeaveArgs, ReportArgs, SkillContext, skill, skills_prompt
from pydantic import BaseModel


class EchoArgs(BaseModel):
    text: str = ""


def test_builtin_skills_are_registered() -> None:
    assert "leave_doc" in SKILLS
    assert "report_xlsx" in SKILLS
    assert SKILLS["leave_doc"].schema is LeaveArgs
    assert SKILLS["report_xlsx"].schema is ReportArgs


def test_duplicate_skill_rejected() -> None:
    with pytest.raises(ValueError):

        @skill("leave_doc", "duplicate", LeaveArgs)
        async def duplicate(args: LeaveArgs, ctx: SkillContext) -> None:
            return None


def test_skill_must_be_async() -> None:
    with pytest.raises(TypeError):

        @skill("sync_skill", "bad", EchoArgs)
        def sync_skill(args: EchoArgs, ctx: SkillContext) -> None:
            return None


def test_prompt_is_generated_from_registry() -> None:
    prompt = skills_prompt()
    assert "leave_doc" in prompt
    assert "report_xlsx" in prompt
    assert "args_schema" in prompt

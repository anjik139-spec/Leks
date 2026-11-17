"""Persona configuration tests."""

from __future__ import annotations

from pathlib import Path

from bot.llm.prompts import PromptRepository

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def test_adult_flirt_mode_is_sfw() -> None:
    """The adult flirt mode is admin-only and explicitly SFW."""
    prompts = PromptRepository(CONFIG_DIR)

    mode = prompts.mode("flirt")
    assert "SFW" in mode.prompt
    assert "без наготы" in mode.prompt
    assert mode.command == ""


def test_mat_mode_is_internal_only() -> None:
    """The mat mode is triggered by profanity, not by a slash command."""
    prompts = PromptRepository(CONFIG_DIR)

    mode = prompts.mode("mat")
    assert mode.command == ""
    assert prompts.mode_by_command("mat") is None


def test_only_mat_persona_remains() -> None:
    """All previous personas are removed; the mat style is the default."""
    prompts = PromptRepository(CONFIG_DIR)

    assert prompts.default_persona == "mat"
    assert len(prompts.personas) == 1
    persona = prompts.personas["mat"]
    assert persona.title == "Мат"
    assert persona.emoji == "🤬"
    assert "В КАЖДОМ ответе" in persona.system_prompt
    assert "гипербола" in persona.system_prompt
    assert "не оскорбляй" in persona.system_prompt.lower()

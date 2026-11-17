"""Quiz response parser tests."""

from __future__ import annotations

from pathlib import Path

from bot.llm.prompts import PromptRepository
from bot.llm.quiz import format_quiz, parse_quiz

VALID_QUIZ = """**ВОПРОС:** Какая планета самая горячая?
1) **Меркурий**
2) **Венера**
3) **Марс**
4) **Юпитер**
**ОТВЕТ:** 2
**ПОЯСНЕНИЕ:** На Венере сильный парниковый эффект.
"""


def test_parse_valid_quiz() -> None:
    """Strict format with Markdown emphasis is parsed."""
    quiz = parse_quiz(VALID_QUIZ)
    assert quiz is not None
    assert quiz.question == "Какая планета самая горячая?"
    assert quiz.options[1] == "Венера"
    assert quiz.correct_index == 1
    assert "парниковый" in quiz.explanation


def test_parse_quiz_with_code_fence() -> None:
    """Models often wrap output in a fence; it must not break parsing."""
    quiz = parse_quiz(f"```\n{VALID_QUIZ}\n```")
    assert quiz is not None
    assert len(quiz.options) == 4


def test_parse_invalid_quiz_returns_none() -> None:
    """Missing options produce no broken quiz UI."""
    assert parse_quiz("ВОПРОС: Что? 1) Да 2) Нет ОТВЕТ: 1") is None
    assert parse_quiz("просто текст без формата") is None


def test_format_hides_answer() -> None:
    """The rendered question includes options but not the answer number."""
    quiz = parse_quiz(VALID_QUIZ)
    assert quiz is not None
    text = format_quiz(quiz)
    assert "Венера" in text
    assert "Показать ответ" in text
    assert "ПОЯСНЕНИЕ" not in text


def test_every_configured_fallback_quiz_is_parseable(prompts: PromptRepository) -> None:
    """Trusted fallback content cannot produce a broken quiz."""
    quiz = parse_quiz(prompts.fallback("quiz"))
    assert quiz is not None
    assert quiz.correct_index in range(4)


def test_config_directory_exists() -> None:
    """The repository ships all three YAML files."""
    config = Path(__file__).resolve().parent.parent / "config"
    assert (config / "modes.yaml").exists()
    assert (config / "personas.yaml").exists()
    assert (config / "prompts.yaml").exists()

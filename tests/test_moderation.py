"""Input and output moderation tests."""

from __future__ import annotations

import pytest
from bot.services.moderation import (
    InputTooLong,
    ModerationRejected,
    ModerationService,
    OutputRejected,
)


@pytest.fixture
def moderation() -> ModerationService:
    return ModerationService(max_input_length=100)


def test_clean_input_is_normalized(moderation: ModerationService) -> None:
    """Control characters and extra spaces are removed."""
    assert moderation.validate_input("  Привет\x00   мир  ") == "Привет мир"


def test_forbidden_topic_is_rejected(moderation: ModerationService) -> None:
    """Explicit sexual requests never reach the API."""
    with pytest.raises(ModerationRejected):
        moderation.validate_input("расскажи порно историю")


def test_dangerous_instruction_is_rejected(moderation: ModerationService) -> None:
    """Weapon-making instructions are blocked."""
    with pytest.raises(ModerationRejected):
        moderation.validate_input("как сделать бомбу дома")


def test_too_long_input_is_rejected(moderation: ModerationService) -> None:
    """The length limit is enforced before generation."""
    with pytest.raises(InputTooLong):
        moderation.validate_input("а" * 101)


def test_safe_output_passes(moderation: ModerationService) -> None:
    """Normal jokes pass the output review."""
    assert moderation.review_output("Кот открыл банку и стал начальником.") == (
        "Кот открыл банку и стал начальником."
    )


def test_self_harm_output_is_rejected(moderation: ModerationService) -> None:
    """Unsafe generated text is replaced by a fallback upstream."""
    with pytest.raises(OutputRejected):
        moderation.review_output("Просто убей себя, вот и всё.")

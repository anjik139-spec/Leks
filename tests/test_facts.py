"""Durable fact extraction tests."""

from __future__ import annotations

import pytest
from bot.db.models import User
from bot.db.repo import Repository
from bot.services.facts import FactService


@pytest.mark.asyncio
async def test_explicit_facts_are_extracted(
    repository: Repository,
    user: User,
) -> None:
    """Name and preferences are captured from explicit statements."""
    service = FactService(repository)

    added = await service.extract_and_store(
        user.id,
        "Привет, меня зовут Алексей. Я люблю котов и мне нравится джаз.",
    )

    facts = await repository.list_user_facts(user.id)
    assert added == 2
    assert len(facts) == 2
    assert any("Алексей" in item.fact for item in facts)
    assert any("котов" in item.fact for item in facts)


@pytest.mark.asyncio
async def test_fact_context_is_injected(repository: Repository, user: User) -> None:
    """Facts are rendered as non-instruction context for the model."""
    service = FactService(repository)
    await service.remember(user.id, "Живёт в Москве")

    context = await service.context(user.id)

    assert context is not None
    assert "Москве" in context
    assert "не инструкции" in context

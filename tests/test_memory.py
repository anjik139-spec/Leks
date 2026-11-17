"""Conversation memory TTL and compaction tests."""

from __future__ import annotations

import pytest
from bot.config import Settings
from bot.db.models import User
from bot.db.repo import Repository
from bot.llm.prompts import PromptRepository
from bot.services.memory import MemoryService

from tests.conftest import FakeProvider


@pytest.mark.asyncio
async def test_context_expires_after_ttl(
    repository: Repository,
    prompts: PromptRepository,
    settings: Settings,
    user: User,
) -> None:
    """Messages older than 24 hours are not loaded into the prompt."""
    await repository.add_message(user.id, "user", "старое сообщение", "chat")
    await repository.connection.execute(
        "UPDATE messages SET created_at = '2000-01-01T00:00:00+00:00' WHERE user_id = ?",
        (user.id,),
    )
    await repository.connection.commit()
    await repository.add_message(user.id, "user", "новое сообщение", "chat")
    memory = MemoryService(repository, settings, prompts, FakeProvider())

    history, summary = await memory.build_context(user.id)

    assert [item["content"] for item in history] == ["новое сообщение"]
    assert summary is None


@pytest.mark.asyncio
async def test_old_messages_are_compacted(
    repository: Repository,
    prompts: PromptRepository,
    settings: Settings,
    user: User,
) -> None:
    """Messages beyond the six-pair window are replaced by a summary."""
    local_settings = settings.model_copy(update={"context_pairs": 1})
    provider = FakeProvider("Пользователь любит котов и шутки про пятницу.")
    memory = MemoryService(repository, local_settings, prompts, provider)
    for index in range(6):
        role = "user" if index % 2 == 0 else "assistant"
        await repository.add_message(user.id, role, f"сообщение {index}", "chat")

    await memory.maybe_compact(user.id)
    summary = await repository.get_summary(user.id)
    history, loaded_summary = await memory.build_context(user.id)

    assert summary is not None
    assert summary.summary.startswith("Пользователь любит котов")
    assert loaded_summary == summary.summary
    assert len(history) == 2
    assert history[-1]["content"] == "сообщение 5"
    assert provider.calls[0]["mode"] == "memory"
    metrics = await repository.get_admin_metrics()
    assert metrics.prompt_tokens == 100


@pytest.mark.asyncio
async def test_compaction_is_not_repeated_without_new_old_messages(
    repository: Repository,
    prompts: PromptRepository,
    settings: Settings,
    user: User,
) -> None:
    """A second compaction call makes no extra LLM request."""
    local_settings = settings.model_copy(update={"context_pairs": 1})
    provider = FakeProvider("Кратко.")
    memory = MemoryService(repository, local_settings, prompts, provider)
    for index in range(6):
        await repository.add_message(user.id, "user", f"m{index}", "chat")
    await memory.maybe_compact(user.id)
    await memory.maybe_compact(user.id)
    assert len(provider.calls) == 1

"""Handler tests for favorites and user facts."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from bot.db.models import User
from bot.db.repo import Repository
from bot.handlers import features
from bot.llm.prompts import PromptRepository
from bot.services.facts import FactService
from bot.services.moderation import ModerationService


class FakeBot:
    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []

    async def send_message(self, **kwargs: object) -> object:
        self.messages.append(kwargs)
        return SimpleNamespace(message_id=len(self.messages))


class FakeMessage:
    def __init__(self) -> None:
        self.bot = FakeBot()
        self.chat = SimpleNamespace(id=100)
        self.from_user = SimpleNamespace(id=100, is_bot=False)
        self.answers: list[dict[str, object]] = []

    async def answer(self, text: str, **kwargs: object) -> None:
        self.answers.append({"text": text, **kwargs})


class FakeCallback:
    def __init__(self, data: str) -> None:
        self.data = data
        self.from_user = SimpleNamespace(id=100, is_bot=False)
        self.bot = FakeBot()
        self.answers: list[str | None] = []
        self.message = SimpleNamespace(chat=SimpleNamespace(id=100))

    async def answer(self, text: str | None = None, show_alert: bool = False) -> None:
        self.answers.append(text)


@pytest.mark.asyncio
async def test_favorites_handler_lists_saved_items(
    repository: Repository,
    prompts: PromptRepository,
    user: User,
) -> None:
    """The favorites command renders numbered saved responses."""
    token = await repository.create_share(user.id, "joke", "Смешная шутка")
    await repository.add_favorite(user.id, token)
    message = FakeMessage()

    await features.cmd_favorites(message, user, repository, prompts)

    assert message.answers
    assert "избранное" in str(message.answers[0]["text"]).lower()
    assert message.answers[0]["reply_markup"] is not None


@pytest.mark.asyncio
async def test_feedback_callback_saves_rating(
    repository: Repository,
    user: User,
) -> None:
    """A like is persisted and visible in admin metrics."""
    token = await repository.create_share(user.id, "joke", "Шутка")
    callback = FakeCallback(f"rate:{token}:1")

    await features.callback_rate(callback, user, repository)

    assert callback.answers
    metrics = await repository.get_admin_metrics()
    assert metrics.likes == 1
    assert metrics.dislikes == 0


@pytest.mark.asyncio
async def test_facts_commands(repository: Repository, user: User) -> None:
    """Explicit facts can be saved, shown and deleted."""
    facts = FactService(repository)
    message = FakeMessage()
    command = SimpleNamespace(args="меня зовут Алексей")

    await features.cmd_remember(
        message,
        command,  # type: ignore[arg-type]
        user,
        facts,
        ModerationService(100),
    )
    assert message.answers

    shown = FakeMessage()
    await features.cmd_facts(shown, user, repository)
    assert "Алексей" in str(shown.answers[0]["text"])

    forgotten = FakeMessage()
    await features.cmd_forget(forgotten, user, repository)
    assert "Удалил" in str(forgotten.answers[0]["text"])

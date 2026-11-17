"""Handler-level tests with mocked Telegram I/O and a fake LLM."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from aiogram.filters import CommandObject
from bot import texts
from bot.config import Settings
from bot.db.models import User
from bot.db.repo import Repository
from bot.handlers import admin, modes
from bot.llm.prompts import PromptRepository
from bot.services.generation import GenerationService
from bot.services.limits import LimitsService
from bot.services.memory import MemoryService
from bot.services.moderation import ModerationService

from tests.conftest import FakeProvider


class FakeBot:
    """Captures outgoing Telegram calls."""

    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []
        self.actions: list[dict[str, object]] = []

    async def send_message(self, **kwargs: object) -> object:
        self.messages.append(kwargs)
        return SimpleNamespace(message_id=len(self.messages))

    async def send_chat_action(self, **kwargs: object) -> bool:
        self.actions.append(kwargs)
        return True


class FakeMessage:
    """Minimal message surface used by direct handler calls."""

    def __init__(self) -> None:
        self.bot = FakeBot()
        self.chat = SimpleNamespace(id=100)
        self.from_user = SimpleNamespace(id=100, is_bot=False)
        self.answers: list[str] = []

    async def answer(self, text: str, **kwargs: object) -> None:
        self.answers.append(text)


class FakeCallback:
    """Minimal callback surface for persona selection."""

    def __init__(self, data: str) -> None:
        self.data = data
        self.from_user = SimpleNamespace(id=100, is_bot=False)
        self.bot = FakeBot()
        self.answers: list[str] = []
        self.edits: list[str] = []
        self.message = SimpleNamespace(chat=SimpleNamespace(id=100))
        callback = self

        async def edit_text(text: str, **kwargs: object) -> None:
            callback.edits.append(text)

        self.message.edit_text = edit_text

    async def answer(self, text: str | None = None, show_alert: bool = False) -> None:
        self.answers.append(text or "")


def _build_service(
    repository: Repository,
    prompts: PromptRepository,
    settings: Settings,
    provider: FakeProvider,
) -> tuple[GenerationService, LimitsService, ModerationService]:
    moderation = ModerationService(settings.max_input_length)
    limits = LimitsService(repository, settings)
    memory = MemoryService(repository, settings, prompts, provider)
    generation = GenerationService(
        repository=repository,
        prompts=prompts,
        provider=provider,
        memory=memory,
        moderation=moderation,
        settings=settings,
    )
    return generation, limits, moderation


@pytest.mark.asyncio
async def test_joke_handler_sends_response_and_consumes_quota(
    repository: Repository,
    prompts: PromptRepository,
    settings: Settings,
    user: User,
) -> None:
    """The /joke command generates, sends buttons and increments the counter."""
    provider = FakeProvider("Шутка про котов.")
    generation, limits, moderation = _build_service(repository, prompts, settings, provider)
    message = FakeMessage()
    command = CommandObject(prefix="/", command="joke", args="коты")

    await modes.cmd_joke(message, command, user, generation, limits, moderation, settings)

    assert message.bot.actions
    assert message.bot.actions[0]["action"] == "typing"
    assert len(message.bot.messages) == 1
    assert message.bot.messages[0]["text"] == "Шутка про котов."
    assert "reply_markup" in message.bot.messages[0]
    assert await repository.get_day_count(user.id) == 1


@pytest.mark.asyncio
async def test_cooldown_is_enforced_between_commands(
    repository: Repository,
    prompts: PromptRepository,
    settings: Settings,
    user: User,
) -> None:
    """A second command within three seconds does not call the LLM twice."""
    provider = FakeProvider("Первый ответ.")
    generation, limits, moderation = _build_service(repository, prompts, settings, provider)
    message = FakeMessage()
    command = CommandObject(prefix="/", command="joke", args="")

    await modes.cmd_joke(message, command, user, generation, limits, moderation, settings)
    await modes.cmd_joke(message, command, user, generation, limits, moderation, settings)

    assert len(provider.calls) == 1
    assert any("Не так быстро" in str(item.get("text")) for item in message.bot.messages)
    assert await repository.get_day_count(user.id) == 1


@pytest.mark.asyncio
async def test_admin_command_rejects_regular_user(
    repository: Repository,
    prompts: PromptRepository,
    settings: Settings,
    user: User,
) -> None:
    """Non-admin users cannot read the dashboard."""
    message = FakeMessage()

    await admin.cmd_admin(message, user, settings, repository, prompts)

    assert message.answers == [texts.ADMIN_DENIED]


@pytest.mark.asyncio
async def test_admin_command_works_for_admin(
    repository: Repository,
    prompts: PromptRepository,
    settings: Settings,
    user: User,
) -> None:
    """An ADMIN_IDS member sees the aggregate dashboard."""
    admin_user = await repository.get_or_create_user(tg_id=999, username="boss")
    message = FakeMessage()

    await admin.cmd_admin(message, admin_user, settings, repository, prompts)

    assert message.answers
    assert "Админка" in message.answers[0]

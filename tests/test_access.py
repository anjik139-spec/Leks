"""Role-based access restrictions for costly features."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from aiogram.enums import ChatType
from bot import texts
from bot.access import can_generate_images, can_search, is_admin, text_limit
from bot.config import Settings
from bot.db.models import User
from bot.db.repo import Repository
from bot.handlers import modes
from bot.handlers.images import run_image_generation
from bot.handlers.modes import _run_generation, _run_grounded


class FakeBot:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    async def send_message(self, **kwargs: Any) -> None:
        self.messages.append(kwargs)


class FakeMessage:
    def __init__(self, text: str) -> None:
        self.text = text
        self.bot = FakeBot()
        self.chat = SimpleNamespace(id=1, type=ChatType.PRIVATE)
        self.from_user = SimpleNamespace(id=999)
        self.reply_to_message = None
        self.answers: list[str] = []

    async def answer(self, text: str, **kwargs: Any) -> None:
        self.answers.append(text)


@pytest.mark.asyncio
async def test_admin_role_and_limits(
    settings: Settings, user: User, repository: Repository
) -> None:
    """Only configured admin IDs bypass owner-only rules and length caps."""
    admin = await repository.get_or_create_user(tg_id=999, username="admin")

    assert is_admin(admin, settings) is True
    assert is_admin(user, settings) is False
    assert text_limit(admin, settings) == settings.max_input_length
    assert text_limit(user, settings) == settings.non_admin_max_input_length
    assert can_generate_images(admin, settings) is True
    assert can_generate_images(user, settings) is False
    assert can_search(admin, settings) is True
    assert can_search(user, settings) is False


@pytest.mark.asyncio
async def test_image_generation_is_admin_only(
    settings: Settings,
    user: User,
    repository: Repository,
) -> None:
    """A non-admin image request is rejected before any image service call."""
    bot = FakeBot()

    await run_image_generation(
        bot=bot,  # type: ignore[arg-type]
        chat_id=1,
        user=user,
        prompt="кот",
        repository=repository,
        images=None,  # type: ignore[arg-type]
        generation=None,  # type: ignore[arg-type]
        limits=None,  # type: ignore[arg-type]
        moderation=None,  # type: ignore[arg-type]
        settings=settings,
    )

    assert bot.messages == [{"chat_id": 1, "text": texts.ADMIN_ONLY_IMAGE}]


@pytest.mark.asyncio
async def test_search_is_admin_only(
    settings: Settings,
    user: User,
    repository: Repository,
) -> None:
    """A restricted deployment can still require admin for search."""
    bot = FakeBot()
    restricted = settings.model_copy(update={"search_admin_only": True})

    await _run_grounded(
        bot=bot,  # type: ignore[arg-type]
        chat_id=1,
        user=user,
        query="новости",
        mode_key="search",
        generation=None,  # type: ignore[arg-type]
        limits=None,  # type: ignore[arg-type]
        moderation=None,  # type: ignore[arg-type]
        repository=repository,
        executor=lambda: None,  # type: ignore[arg-type,return-value]
        settings=restricted,
    )

    assert bot.messages == [{"chat_id": 1, "text": texts.ADMIN_ONLY_SEARCH}]


@pytest.mark.asyncio
async def test_long_text_is_rejected_for_non_admin(
    settings: Settings,
    user: User,
) -> None:
    """A non-admin cannot send a prompt above the short-text limit."""
    bot = FakeBot()

    await _run_generation(
        bot=bot,  # type: ignore[arg-type]
        chat_id=1,
        user=user,
        mode_key="chat",
        topic="а" * (settings.non_admin_max_input_length + 1),
        generation=None,  # type: ignore[arg-type]
        limits=None,  # type: ignore[arg-type]
        moderation=None,  # type: ignore[arg-type]
        settings=settings,
    )

    assert bot.messages[0]["text"] == texts.NON_ADMIN_TEXT_LIMIT.format(
        limit=settings.non_admin_max_input_length
    )


def test_image_button_is_hidden_for_regular_menu() -> None:
    """The menu builder can omit the image button for non-admins."""
    from bot.keyboards import main_menu

    menu = main_menu([], "Кот", show_image=False)
    callbacks = [
        button.callback_data
        for row in menu.inline_keyboard
        for button in row
        if button.callback_data
    ]

    assert "image_random" not in callbacks


@pytest.mark.asyncio
async def test_search_words_do_not_trigger_web_without_command(
    settings: Settings,
    repository: Repository,
) -> None:
    """Explicit search is forced, unless search is disabled entirely."""
    admin = await repository.get_or_create_user(tg_id=999, username="admin")
    message = FakeMessage("найди свежие новости")
    disabled = settings.model_copy(update={"search_enabled": False})

    await modes.free_form(
        message,  # type: ignore[arg-type]
        admin,
        generation=None,  # type: ignore[arg-type]
        limits=None,  # type: ignore[arg-type]
        moderation=None,  # type: ignore[arg-type]
        repository=repository,
        images=None,  # type: ignore[arg-type]
        settings=disabled,
        bot_username="test_bot",
    )

    assert message.answers == [texts.SEARCH_DISABLED]

"""Router integration through aiogram's update pipeline with a fake session."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.methods import AnswerInlineQuery, SendMessage
from aiogram.methods.base import TelegramMethod
from aiogram.types import Chat, InlineQuery, Message, Update
from aiogram.types import User as TgUser
from bot.config import Settings
from bot.db.models import User
from bot.db.repo import Repository
from bot.handlers import admin, inline, modes, start
from bot.llm.prompts import PromptRepository
from bot.middlewares import UserMiddleware
from bot.services.generation import GenerationService
from bot.services.limits import LimitsService
from bot.services.memory import MemoryService
from bot.services.moderation import ModerationService

from tests.conftest import FakeProvider


class CapturingSession(BaseSession):
    """Answer Telegram API calls locally and keep the request methods."""

    def __init__(self) -> None:
        super().__init__()
        self.methods: list[TelegramMethod[Any]] = []

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[Any],
        timeout: int | None = None,
    ) -> Any:
        self.methods.append(method)
        if isinstance(method, SendMessage):
            chat_id = method.chat_id if isinstance(method.chat_id, int) else 100
            return Message(
                message_id=1,
                date=datetime.now(UTC),
                chat=Chat(id=chat_id, type="private"),
                text=method.text,
            )
        return True

    async def stream_content(
        self,
        url: str,
        headers: dict[str, Any] | None = None,
        timeout: int = 30,
        chunk_size: int = 65536,
        raise_for_status: bool = True,
    ) -> AsyncGenerator[bytes, None]:
        yield b""

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_joke_update_reaches_handler_and_replies(
    repository: Repository,
    prompts: PromptRepository,
    settings: Settings,
    user: User,
) -> None:
    """A full /joke update flows through middleware and routers to a reply."""
    provider = FakeProvider("Интеграционная шутка.")
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
    session = CapturingSession()
    bot = Bot(token=settings.bot_token_value, session=session)
    dispatcher = Dispatcher()
    dispatcher["settings"] = settings
    dispatcher["repository"] = repository
    dispatcher["prompts"] = prompts
    dispatcher["moderation"] = moderation
    dispatcher["limits"] = limits
    dispatcher["generation"] = generation
    dispatcher["bot_username"] = "LexaGenesisBot"
    user_middleware = UserMiddleware(repository, prompts, settings)
    dispatcher.message.outer_middleware(user_middleware)
    dispatcher.callback_query.outer_middleware(user_middleware)
    dispatcher.include_router(start.router)
    dispatcher.include_router(admin.router)
    dispatcher.include_router(modes.router)
    dispatcher.include_router(inline.router)

    update = Update(
        update_id=1,
        message=Message(
            message_id=1,
            date=datetime.now(UTC),
            chat=Chat(id=100, type="private"),
            from_user=TgUser(id=100, is_bot=False, first_name="Тест"),
            text="/joke про котов",
        ),
    )
    try:
        await dispatcher.feed_update(bot, update)
        sends = [method for method in session.methods if isinstance(method, SendMessage)]
        assert len(sends) == 1
        assert sends[0].text == "Интеграционная шутка."
        markup = sends[0].reply_markup
        assert markup is None
        cursor = await repository.connection.execute(
            "SELECT token FROM shares ORDER BY rowid DESC LIMIT 1"
        )
        row = await cursor.fetchone()
        assert row is not None
        share_query = f"share_{row[0]}"

        inline_update = Update(
            update_id=2,
            inline_query=InlineQuery(
                id="inline-1",
                from_user=TgUser(id=100, is_bot=False, first_name="Тест"),
                query=share_query,
                offset="",
            ),
        )
        await dispatcher.feed_update(bot, inline_update)
    finally:
        await bot.session.close()

    inline_answers = [method for method in session.methods if isinstance(method, AnswerInlineQuery)]
    assert len(inline_answers) == 1
    results = inline_answers[0].results
    assert results
    content = results[0].input_message_content
    assert content.message_text == "Интеграционная шутка."
    assert await repository.get_day_count(user.id) == 1

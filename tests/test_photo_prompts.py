"""Vision-assisted photo prompt tests."""

from __future__ import annotations

import pytest
from bot.config import Settings
from bot.db.models import User
from bot.db.repo import Repository
from bot.llm.base import ChatMessage, GenerationResult, LLMUnavailableError, Provider
from bot.services.moderation import ModerationService
from bot.services.photo_prompts import PhotoPromptService


class FakeVisionProvider(Provider):
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[dict[str, object]] = []

    async def generate(
        self,
        messages: list[ChatMessage] | tuple[ChatMessage, ...],
        *,
        temperature: float,
        max_tokens: int,
        mode: str,
        model: str | None = None,
        thinking: bool | None = None,
        reasoning_effort: str | None = None,
    ) -> GenerationResult:
        raise NotImplementedError

    async def analyze_image(
        self,
        *,
        image_bytes: bytes,
        mime_type: str,
        instruction: str,
        model: str,
    ) -> GenerationResult:
        self.calls.append({"bytes": len(image_bytes), "mime": mime_type, "model": model})
        if self.fail:
            raise LLMUnavailableError("vision down", error_type="APIConnectionError")
        return GenerationResult(
            text="cinematic portrait, warm light, detailed jacket, city background",
            model=model,
            prompt_tokens=400,
            completion_tokens=30,
            latency_ms=100,
            cost_est=0.0002,
        )


@pytest.mark.asyncio
async def test_photo_prompt_uses_vision_and_records_usage(
    repository: Repository,
    settings: Settings,
    user: User,
) -> None:
    """The vision model builds the edit prompt and its tokens are billed."""
    provider = FakeVisionProvider()
    service = PhotoPromptService(
        provider=provider,
        repository=repository,
        moderation=ModerationService(settings.max_input_length),
        settings=settings,
    )

    prompt = await service.build_edit_prompt(
        user=user,
        image_bytes=b"\xff\xd8" + b"x" * 2048,
        mime_type="image/jpeg",
        caption="в стиле киберпанка",
    )

    assert prompt.startswith("cinematic")
    assert provider.calls[0]["mime"] == "image/jpeg"
    assert provider.calls[0]["model"] == settings.deepseek_vision_model
    stats = await repository.get_user_stats(user, settings.daily_limit)
    assert stats.prompt_tokens == 400


@pytest.mark.asyncio
async def test_photo_prompt_falls_back_to_caption(
    repository: Repository,
    settings: Settings,
    user: User,
) -> None:
    """A vision outage must not block the photo edit."""
    provider = FakeVisionProvider(fail=True)
    service = PhotoPromptService(
        provider=provider,
        repository=repository,
        moderation=ModerationService(settings.max_input_length),
        settings=settings,
    )

    prompt = await service.build_edit_prompt(
        user=user,
        image_bytes=b"\xff\xd8" + b"x" * 2048,
        mime_type="image/jpeg",
        caption="аниме-портрет",
    )

    assert prompt.startswith("аниме-портрет")

"""Image provider tests with a mocked HTTP transport."""

from __future__ import annotations

import httpx
import pytest
from bot.config import Settings
from bot.services.images import ImageService, ImageUnavailableError


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_image_generation_uses_pollinations(settings: Settings) -> None:
    """The free provider is called with the configured model and size."""

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "image.pollinations.ai"
        assert "/prompt/" in request.url.path
        assert request.url.params["model"] == settings.image_model
        assert request.url.params["width"] == str(settings.image_size)
        return httpx.Response(
            200,
            content=b"\xff\xd8" + b"x" * 2048,
            headers={"content-type": "image/jpeg"},
        )

    client = _client(handler)
    service = ImageService(settings, client=client)
    try:
        image = await service.generate("кот-астронавт")
    finally:
        await client.aclose()

    assert image.extension == "jpg"
    assert image.mime_type == "image/jpeg"
    assert len(image.data) > 1024
    assert image.model.startswith("pollinations/")


@pytest.mark.asyncio
async def test_image_rejects_non_image_response(settings: Settings) -> None:
    """HTML error pages are not sent to Telegram as photos."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>error</html>", headers={"content-type": "text/html"})

    client = _client(handler)
    service = ImageService(settings, client=client)
    try:
        with pytest.raises(ImageUnavailableError):
            await service.generate("cat")
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_image_prompt_length_is_limited(settings: Settings) -> None:
    """Too-long prompts fail before any HTTP call."""
    called = False

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(500)

    client = _client(handler)
    service = ImageService(settings, client=client)
    try:
        with pytest.raises(ValueError):
            await service.generate("x" * (settings.image_max_prompt_length + 1))
    finally:
        await client.aclose()
    assert called is False

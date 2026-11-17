"""Ranvik image-to-image editing client tests."""

from __future__ import annotations

import base64
import json

import httpx
import pytest
from bot.config import Settings
from bot.services.image_edit import ImageEditUnavailableError, RanvikImageEditor
from pydantic import SecretStr


def _settings(settings: Settings) -> Settings:
    return settings.model_copy(update={"ranvik_api_key": SecretStr("rk_live_test")})


@pytest.mark.asyncio
async def test_ranvik_edit_sends_reference_and_downloads_result(settings: Settings) -> None:
    """The reference is sent as a data URL and the CDN image is returned."""
    calls: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.method == "POST":
            body = json.loads(request.content)
            assert body["model"] == settings.image_edit_model
            assert body["inputs"]["referenceImages"][0].startswith("data:image/jpeg;base64,")
            return httpx.Response(
                200,
                json={"data": [{"url": "https://cdn.example.com/result.png"}]},
            )
        return httpx.Response(
            200,
            content=b"\x89PNG" + b"x" * 2048,
            headers={"content-type": "image/png"},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    editor = RanvikImageEditor(_settings(settings), client=client)
    try:
        assert editor.configured is True
        image = await editor.edit(
            image_bytes=b"\xff\xd8" + b"x" * 2048,
            mime_type="image/jpeg",
            prompt="в стиле киберпанка",
        )
    finally:
        await client.aclose()

    assert len(calls) == 2
    assert calls[0].headers["authorization"].startswith("Bearer rk_live")
    assert image.extension == "png"
    assert image.data.startswith(b"\x89PNG")


@pytest.mark.asyncio
async def test_ranvik_edit_reports_api_error(settings: Settings) -> None:
    """Provider errors are converted into a domain error."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    editor = RanvikImageEditor(_settings(settings), client=client)
    try:
        with pytest.raises(ImageEditUnavailableError) as info:
            await editor.edit(image_bytes=b"x" * 2048, mime_type="image/jpeg", prompt="стиль")
    finally:
        await client.aclose()

    assert info.value.status_code == 401


@pytest.mark.asyncio
async def test_ranvik_without_key_is_not_configured(settings: Settings) -> None:
    """The editor says it is unconfigured when no key exists."""
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500)))
    editor = RanvikImageEditor(settings, client=client)
    try:
        assert editor.configured is False
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_ranvik_base64_response_is_supported(settings: Settings) -> None:
    """A provider may return b64_json instead of a URL."""
    encoded = base64.b64encode(b"\x89PNG" + b"x" * 2048).decode("ascii")

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"b64_json": encoded}]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    editor = RanvikImageEditor(_settings(settings), client=client)
    try:
        image = await editor.edit(
            image_bytes=b"\xff\xd8" + b"x" * 2048,
            mime_type="image/jpeg",
            prompt="",
        )
    finally:
        await client.aclose()

    assert image.mime_type == "image/png"
    assert image.data.startswith(b"\x89PNG")

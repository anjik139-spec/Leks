"""Tests for text splitting and Markdown fallback."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from bot.utils import clip_text, plain_excerpt, send_long_message, split_text


def test_short_text_is_not_split() -> None:
    """Text below the limit is returned unchanged as one chunk."""
    assert split_text("Привет, мир!", limit=100) == ["Привет, мир!"]


def test_long_text_splits_without_breaking_words() -> None:
    """Chunks respect the limit and preserve every word in order."""
    words = [f"слово{i}" for i in range(500)]
    source = " ".join(words)
    chunks = split_text(source, limit=200)

    assert len(chunks) > 1
    assert all(len(chunk) <= 200 for chunk in chunks)
    assert " ".join(chunks).split() == words


def test_split_prefers_paragraph_boundary() -> None:
    """A blank line near the limit is used as the split point."""
    text = "Первый абзац. " * 4 + "\n\n" + "Второй абзац. " * 4
    chunks = split_text(text, limit=70)
    assert len(chunks) >= 2
    assert chunks[0].startswith("Первый абзац.")


def test_split_empty_text() -> None:
    """Whitespace-only text produces no messages."""
    assert split_text("   \n\n  ") == []


def test_clip_text_respects_limit() -> None:
    """Inline content is clipped to Telegram's cap."""
    result = clip_text("а" * 5000, limit=100)
    assert len(result) <= 100
    assert result.endswith("…")


def test_plain_excerpt_collapses_whitespace() -> None:
    """Inline descriptions are single-line and bounded."""
    assert plain_excerpt("a\n\nb\tc", limit=10) == "a b c"


class _FakeBot:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def send_message(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            raise TelegramBadRequest(
                method=MagicMock(),
                message="Bad Request: can't parse entities: unexpected end tag",
            )
        return object()


@pytest.mark.asyncio
async def test_markdown_falls_back_to_plain_text() -> None:
    """A Telegram entity error retries the same chunk without Markdown."""
    bot = _FakeBot()
    await send_long_message(bot, 1, "*сломанный markdown", None)  # type: ignore[arg-type]

    assert len(bot.calls) == 2
    assert bot.calls[0]["parse_mode"] == ParseMode.MARKDOWN
    assert "parse_mode" not in bot.calls[1]
    assert bot.calls[1]["text"] == bot.calls[0]["text"]

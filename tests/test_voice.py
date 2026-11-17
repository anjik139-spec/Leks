"""Voice service text normalization tests."""

from __future__ import annotations

from bot.config import Settings
from bot.services.voice import VoiceService


def test_voice_text_is_cleaned(settings: Settings) -> None:
    """Markdown, links and repeated whitespace are removed before TTS."""
    service = VoiceService(settings)
    text = "**Привет** https://example.com  это   тест `кода`."

    cleaned = service.clean_text(text)

    assert cleaned == "Привет это тест кода."
    assert len(service.clean_text("а" * 2000)) == 900

"""Group addressing tests."""

from __future__ import annotations

from types import SimpleNamespace

from bot import texts
from bot.handlers.modes import (
    _contains_profanity,
    _is_bot_addressed,
    _looks_like_creator_question,
    _looks_like_image_request,
    _looks_like_mat_request,
    _looks_like_search_request,
    _should_handle_free_text,
    _strip_bot_mention,
    _strip_mat_trigger,
)


def _message(text: str, *, reply_to_bot: bool = False) -> SimpleNamespace:
    reply = None
    if reply_to_bot:
        reply = SimpleNamespace(from_user=SimpleNamespace(id=42))
    return SimpleNamespace(
        text=text,
        reply_to_message=reply,
        bot=SimpleNamespace(id=42),
    )


def test_mention_is_detected() -> None:
    assert _is_bot_addressed(_message("привет @LexaGenesisBot"), "LexaGenesisBot") is True


def test_plain_group_message_is_ignored() -> None:
    assert _is_bot_addressed(_message("просто болтаем"), "LexaGenesisBot") is False


def test_reply_to_bot_is_detected() -> None:
    assert _is_bot_addressed(_message("спасибо", reply_to_bot=True), "") is True


def test_mention_is_removed_from_prompt() -> None:
    assert (
        _strip_bot_mention("@LexaGenesisBot расскажи шутку", "LexaGenesisBot") == "расскажи шутку"
    )


def test_private_free_chat_can_be_disabled() -> None:
    assert (
        _should_handle_free_text(
            "private",
            addressed=False,
            group_mention_only=True,
            private_free_chat=False,
        )
        is False
    )
    assert (
        _should_handle_free_text(
            "private",
            addressed=True,
            group_mention_only=True,
            private_free_chat=False,
        )
        is True
    )
    assert (
        _should_handle_free_text(
            "private",
            addressed=False,
            group_mention_only=True,
            private_free_chat=False,
            explicit_request=True,
        )
        is True
    )


def test_group_requires_address_when_enabled() -> None:
    assert (
        _should_handle_free_text(
            "supergroup",
            addressed=False,
            group_mention_only=True,
            private_free_chat=False,
        )
        is False
    )
    assert (
        _should_handle_free_text(
            "supergroup",
            addressed=True,
            group_mention_only=True,
            private_free_chat=False,
        )
        is True
    )


def test_channels_are_ignored() -> None:
    assert (
        _should_handle_free_text(
            "channel",
            addressed=True,
            group_mention_only=False,
            private_free_chat=True,
        )
        is False
    )


def test_search_intent_is_detected() -> None:
    assert _looks_like_search_request("найди последние новости про Python") is True
    assert _looks_like_search_request("погугли погоду в Москве") is True
    assert _looks_like_search_request("расскажи шутку про кота") is False


def test_image_intent_is_detected() -> None:
    assert _looks_like_image_request("нарисуй кота-астронавта") is True
    assert _looks_like_image_request("сгенерируй фото дракона") is True
    assert _looks_like_image_request("расскажи шутку про кота") is False


def test_creator_question_is_detected() -> None:
    assert _looks_like_creator_question("Кто тебя создал?") is True
    assert _looks_like_creator_question("кто твой разработчик") is True
    assert _looks_like_creator_question("Who created you?") is True
    assert _looks_like_creator_question("кто создал Telegram") is False
    assert _looks_like_creator_question("расскажи шутку про кота") is False
    assert texts.CREATOR_ANSWER == "Алексей Клюев — мой бог и создатель. 🙌"


def test_mat_request_is_detected_and_stripped() -> None:
    assert _looks_like_mat_request("выругайся про пробки") is True
    assert _looks_like_mat_request("матюкнись") is True
    assert _looks_like_mat_request("матерись про дедлайн") is True
    assert _looks_like_mat_request("расскажи шутку") is False
    assert _strip_mat_trigger("выругайся про пробки") == "пробки"
    assert _strip_mat_trigger("матюкнись") == "бытовая ситуация"


def test_profanity_is_detected() -> None:
    assert _contains_profanity("да блядь, опять дедлайн") is True
    assert _contains_profanity("ну нахуй эту работу") is True
    assert _contains_profanity("тебе повезло") is False
    assert _contains_profanity("бляха на ремне") is False

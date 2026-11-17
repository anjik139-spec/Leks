"""Repository, persistence and reporting tests."""

from __future__ import annotations

import aiosqlite
import pytest
from bot.config import Settings
from bot.db.migrations import init_database
from bot.db.models import User
from bot.db.repo import Repository


@pytest.mark.asyncio
async def test_persona_survives_reconnect(settings: Settings) -> None:
    """A persona is persisted in SQLite, not in process memory."""
    first_connection = await init_database(settings.db_path)
    first_repo = Repository(first_connection)
    user = await first_repo.get_or_create_user(tg_id=501, username="cat_lover")
    await first_repo.set_persona(user.id, "cat")
    await first_connection.close()

    second_connection = await init_database(settings.db_path)
    second_repo = Repository(second_connection)
    restored = await second_repo.get_user_by_tg_id(501)
    await second_connection.close()

    assert restored is not None
    assert restored.persona == "cat"


@pytest.mark.asyncio
async def test_reset_clears_messages_and_summary_but_keeps_counter(
    repository: Repository,
    user: User,
) -> None:
    """Context reset removes dialog data without resetting quota."""
    await repository.add_message(user.id, "user", "старый вопрос", "chat")
    await repository.add_message(user.id, "assistant", "старый ответ", "chat")
    await repository.save_summary(user.id, "краткое резюме", 2)
    await repository.increment_counter(user.id)

    deleted = await repository.clear_context(user.id)
    messages = await repository.get_recent_messages(user.id, "1970-01-01T00:00:00+00:00")

    assert deleted == 2
    assert messages == []
    assert await repository.get_summary(user.id) is None
    assert await repository.get_day_count(user.id) == 1


@pytest.mark.asyncio
async def test_quiz_answer_can_only_be_revealed_once(
    repository: Repository,
    user: User,
) -> None:
    """The atomic update prevents duplicate answer messages."""
    quiz_id = await repository.create_quiz(
        user_id=user.id,
        question="2 + 2?",
        options=("3", "4", "5", "6"),
        correct_index=1,
        explanation="Четыре.",
    )
    quiz = await repository.get_quiz(quiz_id)
    assert quiz is not None
    assert quiz.options[1] == "4"
    assert await repository.mark_quiz_answered(quiz_id, user.id) is True
    assert await repository.mark_quiz_answered(quiz_id, user.id) is False


@pytest.mark.asyncio
async def test_share_round_trip(repository: Repository, user: User) -> None:
    """Share tokens resolve to the original content."""
    token = await repository.create_share(user.id, "joke", "Смешная шутка")
    share = await repository.get_share(token)
    assert share is not None
    assert share.content == "Смешная шутка"
    assert await repository.get_share("missing") is None


@pytest.mark.asyncio
async def test_favorites_are_unique_and_randomizable(
    repository: Repository,
    user: User,
) -> None:
    """A shared response can be saved once and read back."""
    token = await repository.create_share(user.id, "joke", "Любимая шутка")
    assert await repository.add_favorite(user.id, token) is True
    assert await repository.add_favorite(user.id, token) is False

    items = await repository.list_favorites(user.id)
    assert len(items) == 1
    assert items[0].content == "Любимая шутка"
    assert await repository.get_favorite(user.id, items[0].id) is not None
    assert await repository.random_favorite(user.id) is not None
    assert await repository.count_favorites(user.id) == 1


@pytest.mark.asyncio
async def test_cannot_favorite_another_users_share(
    repository: Repository,
    user: User,
) -> None:
    """Favorites are scoped to the share owner."""
    other = await repository.get_or_create_user(tg_id=777, username="other")
    token = await repository.create_share(other.id, "joke", "Чужая шутка")
    assert await repository.add_favorite(user.id, token) is False


@pytest.mark.asyncio
async def test_daily_quest_completion_and_checkins(
    repository: Repository,
    user: User,
) -> None:
    """Completing a quest records exactly one check-in."""
    quest = await repository.create_daily_quest(user.id, "2026-11-12", "Сделай что-нибудь")
    assert quest.completed_at is None
    assert await repository.complete_daily_quest(user.id, "2026-11-12") is True
    assert await repository.complete_daily_quest(user.id, "2026-11-12") is False

    stored = await repository.get_daily_quest(user.id, "2026-11-12")
    assert stored is not None and stored.completed_at is not None
    assert await repository.get_checkin_days(user.id) == ["2026-11-12"]


@pytest.mark.asyncio
async def test_feedback_is_upserted_and_counted(
    repository: Repository,
    user: User,
) -> None:
    """A response can be rated once and the rating can be changed."""
    token = await repository.create_share(user.id, "joke", "Шутка")
    assert await repository.add_feedback(user.id, token, "joke", 1) is True
    assert await repository.add_feedback(user.id, token, "joke", -1) is True
    other_token = await repository.create_share(user.id, "joke", "Ещё шутка")
    assert await repository.add_feedback(user.id, other_token, "joke", 1) is True

    metrics = await repository.get_admin_metrics()
    assert metrics.likes == 1
    assert metrics.dislikes == 1


@pytest.mark.asyncio
async def test_voice_mode_persists(repository: Repository) -> None:
    """Automatic voice replies can be toggled per chat."""
    assert await repository.is_voice_mode(123) is False
    await repository.set_voice_mode(123, True)
    assert await repository.is_voice_mode(123) is True
    await repository.set_voice_mode(123, False)
    assert await repository.is_voice_mode(123) is False


@pytest.mark.asyncio
async def test_user_facts_are_persisted_and_clearable(
    repository: Repository,
    user: User,
) -> None:
    """Facts are deduplicated, listed and removable."""
    assert await repository.add_user_fact(user.id, "Любит котов") is True
    assert await repository.add_user_fact(user.id, "Любит котов") is False
    facts = await repository.list_user_facts(user.id)
    assert [item.fact for item in facts] == ["Любит котов"]
    assert await repository.clear_user_facts(user.id) == 1
    assert await repository.list_user_facts(user.id) == []


@pytest.mark.asyncio
async def test_user_and_admin_stats(
    repository: Repository,
    user: User,
    settings: Settings,
) -> None:
    """Usage is aggregated for personal and admin dashboards."""
    await repository.increment_counter(user.id)
    await repository.add_usage(
        user_id=user.id,
        mode="joke",
        prompt_tokens=100,
        completion_tokens=50,
        cost_est=0.0001,
        latency_ms=200,
        model="deepseek-flash",
    )
    await repository.add_service_usage(
        kind="broadcast",
        prompt_tokens=20,
        completion_tokens=10,
        cost_est=0.0002,
        latency_ms=150,
        model="deepseek-flash",
    )

    stats = await repository.get_user_stats(user, settings.daily_limit)
    metrics = await repository.get_admin_metrics()

    assert stats.generations_today == 1
    assert stats.prompt_tokens == 100
    assert stats.completion_tokens == 50
    assert stats.quota.remaining == settings.daily_limit - 1
    assert metrics.generations_today == 1
    assert metrics.prompt_tokens == 120
    assert metrics.completion_tokens == 60
    assert metrics.top_modes[0].mode == "joke"


@pytest.mark.asyncio
async def test_migrations_are_idempotent(settings: Settings) -> None:
    """Opening the same database twice does not duplicate schema versions."""
    connection = await init_database(settings.db_path)
    await connection.close()
    connection = await init_database(settings.db_path)
    cursor = await connection.execute("SELECT COUNT(*) FROM schema_migrations")
    row = await cursor.fetchone()
    await connection.close()
    assert row is not None
    assert row[0] == 22


@pytest.mark.asyncio
async def test_subscription_removed_when_bot_is_blocked(
    repository: Repository,
    user: User,
) -> None:
    """A failed delivery removes the subscription by Telegram ID."""
    await repository.subscribe(user.id)
    assert await repository.is_subscribed(user.id) is True
    assert await repository.unsubscribe_by_tg_id(user.tg_id) is True
    assert await repository.is_subscribed(user.id) is False


@pytest.mark.asyncio
async def test_foreign_key_enforcement(database: aiosqlite.Connection) -> None:
    """Messages cannot reference a non-existent user."""
    with pytest.raises(aiosqlite.IntegrityError):
        await database.execute(
            "INSERT INTO messages(user_id, role, content, mode, created_at) "
            "VALUES (?, 'user', 'x', 'chat', '2026-01-01T00:00:00+00:00')",
            (999_999,),
        )

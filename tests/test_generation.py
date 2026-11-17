"""Generation orchestration, fallback and persona tests."""

from __future__ import annotations

import pytest
from bot.config import Settings
from bot.db.models import User
from bot.db.repo import Repository
from bot.llm.base import ChatMessage, GenerationResult, LLMUnavailableError, Provider
from bot.llm.prompts import PromptRepository
from bot.services.facts import FactService
from bot.services.generation import GenerationService
from bot.services.memory import MemoryService
from bot.services.moderation import ModerationRejected, ModerationService
from bot.services.search import SearchBundle, SearchResponse, SearchResult

from tests.conftest import FakeProvider


class FakeSearch:
    """Search double with a fixed result set."""

    def __init__(self) -> None:
        self.queries: list[str] = []

    async def search(self, user_id: int, query: str) -> SearchResponse:
        self.queries.append(query)
        return SearchResponse(
            query=query,
            results=(
                SearchResult(
                    title="Example source",
                    url="https://example.com/source",
                    summary="Useful web summary",
                    snippet="Snippet",
                ),
            ),
            cost_est=0.00075,
            latency_ms=30,
        )

    async def search_many(
        self,
        user_id: int,
        queries: list[str],
        *,
        need_content: bool = True,
        count: int | None = None,
    ) -> SearchBundle:
        self.queries.extend(queries)
        return SearchBundle(
            queries=tuple(queries),
            results=(
                SearchResult(
                    title="Example source",
                    url="https://example.com/source",
                    summary="Useful web summary",
                    snippet="Snippet",
                ),
            ),
            cost_est=0.00075 * len(queries),
            latency_ms=30,
        )

    def format_for_prompt(self, results) -> str:
        return "\n".join(f"[1] {item.title}: {item.summary}" for item in results)


class FailingProvider(Provider):
    """Provider that simulates a complete DeepSeek outage."""

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
        raise LLMUnavailableError("down", error_type="APIConnectionError", status_code=None)


def _service(
    repository: Repository,
    prompts: PromptRepository,
    settings: Settings,
    provider: Provider,
    search=None,
    facts=None,
) -> GenerationService:
    moderation = ModerationService(settings.max_input_length)
    memory = MemoryService(repository, settings, prompts, provider)
    return GenerationService(
        repository=repository,
        prompts=prompts,
        provider=provider,
        memory=memory,
        moderation=moderation,
        settings=settings,
        search=search,
        facts=facts,
    )


@pytest.mark.asyncio
async def test_successful_generation_persists_everything(
    repository: Repository,
    prompts: PromptRepository,
    settings: Settings,
    user: User,
) -> None:
    """A successful generation writes messages, usage, share and last mode."""
    provider = FakeProvider("Кот сказал: мяу. Это и есть бизнес-план.")
    service = _service(repository, prompts, settings, provider)

    outcome = await service.generate(user, "joke", "коты")

    assert outcome.is_fallback is False
    assert outcome.text.startswith("Кот сказал")
    assert outcome.share_token is not None
    assert outcome.quiz_id is None
    assert provider.calls[0]["mode"] == "joke"
    assert provider.calls[0]["model"] == settings.deepseek_model
    assert provider.calls[0]["temperature"] == prompts.effective_temperature("joke", "soul")
    system_prompt = provider.calls[0]["messages"][0]["content"]
    assert "Сейчас" in system_prompt

    messages = await repository.get_recent_messages(user.id, "1970-01-01T00:00:00+00:00")
    assert [item.role for item in messages] == ["user", "assistant"]
    assert messages[0].content == "/joke коты"

    updated = await repository.get_user_by_tg_id(user.tg_id)
    assert updated is not None
    assert updated.last_mode == "joke"
    assert updated.last_topic == "коты"

    share = await repository.get_share(outcome.share_token or "")
    assert share is not None and share.content == outcome.text
    metrics = await repository.get_admin_metrics()
    assert metrics.prompt_tokens == 100
    assert metrics.generations_today == 0  # counters are handler-level, usage is provider-level


@pytest.mark.asyncio
async def test_api_outage_returns_fallback_without_messages(
    repository: Repository,
    prompts: PromptRepository,
    settings: Settings,
    user: User,
) -> None:
    """A full API failure produces pre-written content and a recorded error."""
    service = _service(repository, prompts, settings, FailingProvider())

    outcome = await service.generate(user, "joke", "коты")

    assert outcome.is_fallback is True
    assert outcome.text == prompts.fallback("joke")
    assert outcome.share_token is not None
    messages = await repository.get_recent_messages(user.id, "1970-01-01T00:00:00+00:00")
    assert messages == []
    metrics = await repository.get_admin_metrics()
    assert metrics.api_errors == 1


@pytest.mark.asyncio
async def test_persona_prompt_is_injected(
    repository: Repository,
    prompts: PromptRepository,
    settings: Settings,
    user: User,
) -> None:
    """The persisted persona is used in the system prompt."""
    updated = await repository.set_persona(user.id, "mat")
    assert updated is not None
    provider = FakeProvider("Ну и дела.")
    service = _service(repository, prompts, settings, provider)

    await service.generate(updated, "joke", "блядь, шутка про работу")

    system_prompt = provider.calls[0]["messages"][0]["content"]  # type: ignore[index]
    assert "грубый" in system_prompt.lower()


@pytest.mark.asyncio
async def test_quiz_is_parsed_and_persisted(
    repository: Repository,
    prompts: PromptRepository,
    settings: Settings,
    user: User,
) -> None:
    """A valid quiz exposes an answer button payload and hides the answer."""
    text = (
        "ВОПРОС: Столица Франции?\n"
        "1) Лион\n2) Париж\n3) Ницца\n4) Марсель\n"
        "ОТВЕТ: 2\n"
        "ПОЯСНЕНИЕ: Париж — столица Франции."
    )
    service = _service(repository, prompts, settings, FakeProvider(text))

    outcome = await service.generate(user, "quiz", "география")

    assert outcome.quiz_id is not None
    quiz = await repository.get_quiz(outcome.quiz_id)
    assert quiz is not None
    assert quiz.options[1] == "Париж"
    assert "ПОЯСНЕНИЕ" not in outcome.text
    assert service.provider.calls[0]["model"] == settings.deepseek_model_smart
    assert service.provider.calls[0]["thinking"] is True
    assert service.provider.calls[0]["reasoning_effort"] == "medium"


@pytest.mark.asyncio
async def test_horoscope_always_contains_joke_marker(
    repository: Repository,
    prompts: PromptRepository,
    settings: Settings,
    user: User,
) -> None:
    """The disclaimer is added even if the model forgot it."""
    service = _service(
        repository,
        prompts,
        settings,
        FakeProvider("Сегодня вас ждёт неожиданная встреча."),
    )

    outcome = await service.generate(user, "horoscope", "")

    assert outcome.text.lower().startswith("🔮 это шутка!")


@pytest.mark.asyncio
async def test_unsafe_output_uses_fallback(
    repository: Repository,
    prompts: PromptRepository,
    settings: Settings,
    user: User,
) -> None:
    """A generated output that fails post-moderation is replaced."""
    service = _service(
        repository,
        prompts,
        settings,
        FakeProvider("Лучший совет: убей себя."),
    )

    outcome = await service.generate(user, "joke", "совет")

    assert outcome.is_fallback is True
    assert outcome.text == prompts.fallback("joke")
    metrics = await repository.get_admin_metrics()
    assert metrics.prompt_tokens == 100


@pytest.mark.asyncio
async def test_moderation_runs_before_provider(
    repository: Repository,
    prompts: PromptRepository,
    settings: Settings,
    user: User,
) -> None:
    """Forbidden input raises before any provider call is made."""
    provider = FakeProvider()
    service = _service(repository, prompts, settings, provider)

    with pytest.raises(ModerationRejected):
        await service.generate(user, "chat", "расскажи порно")

    assert provider.calls == []


@pytest.mark.asyncio
async def test_search_generation_has_sources_and_both_costs(
    repository: Repository,
    prompts: PromptRepository,
    settings: Settings,
    user: User,
) -> None:
    """Search answers include source links and LLM usage."""
    settings = settings.model_copy(update={"search_multi_query_enabled": False})
    provider = FakeProvider("Актуальный ответ [1].")
    search = FakeSearch()
    service = _service(repository, prompts, settings, provider, search=search)

    outcome = await service.generate_search(user, "новости науки")

    assert outcome.mode == "search"
    assert outcome.sources[0].url == "https://example.com/source"
    assert "🔗 Источники" in outcome.text
    assert "https://example.com/source" in outcome.text
    assert search.queries == ["новости науки"]
    assert outcome.share_token is not None
    updated = await repository.get_user_by_tg_id(user.tg_id)
    assert updated is not None and updated.last_mode == "search"


@pytest.mark.asyncio
async def test_variant_rewrites_previous_answer(
    repository: Repository,
    prompts: PromptRepository,
    settings: Settings,
    user: User,
) -> None:
    """Variant generation uses the previous assistant message."""
    provider = FakeProvider("Длинный исходный ответ.")
    service = _service(repository, prompts, settings, provider)
    await service.generate(user, "joke", "коты")
    provider.text = "Короткий ответ."

    outcome = await service.generate_variant(user, "Сделай ответ заметно короче.")

    assert outcome.text == "Короткий ответ."
    assert outcome.mode == "joke"
    captured = provider.calls[-1]["messages"]
    assert "Сделай ответ заметно короче" in captured[-1]["content"]
    assert "Длинный исходный ответ." in captured[-1]["content"]
    messages = await repository.get_recent_messages(user.id, "1970-01-01T00:00:00+00:00")
    assert len(messages) == 4


@pytest.mark.asyncio
async def test_facts_and_date_are_injected_into_system_prompt(
    repository: Repository,
    prompts: PromptRepository,
    settings: Settings,
    user: User,
) -> None:
    """Durable facts and current time are part of the model context."""
    facts = FactService(repository)
    await facts.remember(user.id, "Живёт в Москве")
    provider = FakeProvider("Привет!")
    service = _service(repository, prompts, settings, provider, facts=facts)

    await service.generate(user, "chat", "Привет, я люблю котов")

    system_prompt = provider.calls[0]["messages"][0]["content"]
    assert "Живёт в Москве" in system_prompt
    assert "Сейчас" in system_prompt
    stored = await repository.list_user_facts(user.id)
    assert any("котов" in item.fact for item in stored)


@pytest.mark.asyncio
async def test_mat_mode_forces_addendum(
    repository: Repository,
    prompts: PromptRepository,
    settings: Settings,
    user: User,
) -> None:
    """The mat mode appends an explicit permission addendum to the system prompt."""
    provider = FakeProvider("Ну и дедлайн, чтоб его.")
    service = _service(repository, prompts, settings, provider)

    await service.generate(user, "mat", "дедлайн")

    system_prompt = provider.calls[0]["messages"][0]["content"]
    assert "Создатель бота явно разрешил" in system_prompt
    assert "Обязательно используй" in system_prompt


@pytest.mark.asyncio
async def test_search_planner_returns_bounded_unique_queries(
    repository: Repository,
    prompts: PromptRepository,
    settings: Settings,
    user: User,
) -> None:
    """The planner parses line-separated queries and caps their count."""
    provider = FakeProvider("коты в космосе\nкоты астронавты\nкоты NASA\nчетвёртый лишний")
    service = _service(repository, prompts, settings, provider)

    queries = await service._plan_search_queries(user, "коты в космосе")

    assert queries == ["коты в космосе", "коты астронавты", "коты NASA"]
    assert provider.calls[0]["mode"] == "search_plan"
    assert provider.calls[0]["model"] == settings.deepseek_model


@pytest.mark.asyncio
async def test_fact_generation_is_grounded_in_search(
    repository: Repository,
    prompts: PromptRepository,
    settings: Settings,
    user: User,
) -> None:
    """The fact mode can be served from web results with citations."""
    settings = settings.model_copy(update={"search_multi_query_enabled": False})
    provider = FakeProvider("Проверенный факт [1].")
    search = FakeSearch()
    service = _service(repository, prompts, settings, provider, search=search)

    outcome = await service.generate_fact(user, "космос")

    assert outcome.mode == "fact"
    assert outcome.sources
    assert "🔗 Источники" in outcome.text
    assert "проверенный" in search.queries[0]
    assert "факт" in search.queries[0]
    updated = await repository.get_user_by_tg_id(user.tg_id)
    assert updated is not None and updated.last_mode == "fact"


@pytest.mark.asyncio
async def test_image_prompt_is_enhanced_by_llm(
    repository: Repository,
    prompts: PromptRepository,
    settings: Settings,
    user: User,
) -> None:
    """The bot turns a short image idea into a detailed English prompt."""
    provider = FakeProvider("cinematic red fox, golden hour, 35mm photo, highly detailed")
    service = _service(repository, prompts, settings, provider)

    prompt = await service.generate_image_prompt(user, "лиса")

    assert prompt.startswith("cinematic red fox")
    assert provider.calls[-1]["mode"] == "image_prompt"
    stats = await repository.get_user_stats(user, settings.daily_limit)
    assert stats.prompt_tokens == 100


@pytest.mark.asyncio
async def test_image_prompt_can_invent_idea(
    repository: Repository,
    prompts: PromptRepository,
    settings: Settings,
    user: User,
) -> None:
    """An empty idea still produces a prompt for a random picture."""
    provider = FakeProvider("surreal floating library in the clouds, vivid colors")
    service = _service(repository, prompts, settings, provider)

    prompt = await service.generate_image_prompt(user, "")

    assert "library" in prompt
    user_prompt = provider.calls[-1]["messages"][-1]["content"]
    assert "придумай" in user_prompt.lower()


@pytest.mark.asyncio
async def test_daily_generation_does_not_pollute_dialog(
    repository: Repository,
    prompts: PromptRepository,
    settings: Settings,
    user: User,
) -> None:
    """Daily quest generation is one-shot and stored only as usage."""
    provider = FakeProvider("Погладь кота и улыбнись.")
    service = _service(repository, prompts, settings, provider)

    outcome = await service.generate_daily(user)

    assert outcome.text.startswith("Погладь кота")
    assert outcome.mode == "daily"
    assert await repository.get_recent_messages(user.id, "1970-01-01T00:00:00+00:00") == []
    stats = await repository.get_user_stats(user, settings.daily_limit)
    assert stats.prompt_tokens == 100

"""Search API client tests using a mocked HTTP transport."""

from __future__ import annotations

import json

import httpx
import pytest
from bot.config import Settings
from bot.db.models import User
from bot.db.repo import Repository
from bot.services.search import (
    SearchBundle,
    SearchNoResultsError,
    SearchService,
    SearchUnavailableError,
)


def _search_service(
    settings: Settings,
    repository: Repository,
    handler,
) -> tuple[SearchService, httpx.AsyncClient]:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return SearchService(repository, settings, client=client), client


@pytest.mark.asyncio
async def test_search_parses_results_and_records_cost(
    repository: Repository,
    settings: Settings,
    user: User,
) -> None:
    """A successful search is parsed and billed once."""

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/tools/search"
        assert request.headers["authorization"].startswith("Bearer ")
        body = json.loads(request.content)
        assert body["need_content"] is True
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Example result",
                        "url": "https://example.com/article",
                        "summary": "Long summary",
                        "snippet": "Short snippet",
                        "content": "Full page markdown",
                        "date": "2026-01-01T00:00:00+00:00",
                    }
                ]
            },
        )

    service, client = _search_service(settings, repository, handler)
    try:
        response = await service.search(user.id, "test query")
    finally:
        await client.aclose()

    assert len(response.results) == 1
    assert response.results[0].url == "https://example.com/article"
    assert response.results[0].content == "Full page markdown"
    assert response.cost_est == settings.search_price_per_request
    stats = await repository.get_user_stats(user, settings.daily_limit)
    assert stats.cost_est == settings.search_price_per_request
    rendered = service.format_for_prompt(response.results)
    assert "https://example.com/article" in rendered
    assert "Full page markdown" in rendered


@pytest.mark.asyncio
async def test_multi_search_merges_and_deduplicates(
    repository: Repository,
    settings: Settings,
    user: User,
) -> None:
    """Three queries produce one deduplicated result set."""
    bodies: list[dict[str, object]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        bodies.append(body)
        query = str(body["query"])
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": f"Result for {query}",
                        "url": "https://example.com/shared",
                        "summary": "Shared page",
                        "content": "Content " * 10,
                        "rerank_score": 2.0,
                    },
                    {
                        "title": f"Unique {query}",
                        "url": f"https://example.com/{len(bodies)}",
                        "summary": "Unique page",
                        "content": "Unique content",
                        "rerank_score": 1.0,
                    },
                ]
            },
        )

    service, client = _search_service(settings, repository, handler)
    try:
        bundle = await service.search_many(user.id, ["one", "two", "three"])
    finally:
        await client.aclose()

    assert isinstance(bundle, SearchBundle)
    assert len(bodies) == 3
    assert all(body["need_content"] is True for body in bodies)
    assert len(bundle.results) == 4
    assert sum(item.url == "https://example.com/shared" for item in bundle.results) == 1
    assert bundle.cost_est == settings.search_price_per_request * 3


@pytest.mark.asyncio
async def test_empty_search_is_not_billed(
    repository: Repository,
    settings: Settings,
    user: User,
) -> None:
    """Empty result sets are free and handled distinctly."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": []})

    service, client = _search_service(settings, repository, handler)
    try:
        with pytest.raises(SearchNoResultsError):
            await service.search(user.id, "nothing")
    finally:
        await client.aclose()

    stats = await repository.get_user_stats(user, settings.daily_limit)
    assert stats.cost_est == 0


@pytest.mark.asyncio
async def test_search_401_is_not_retried(
    repository: Repository,
    settings: Settings,
    user: User,
) -> None:
    """Authentication errors fail immediately."""
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401, json={"error": {"message": "invalid"}})

    service, client = _search_service(settings, repository, handler)
    try:
        with pytest.raises(SearchUnavailableError) as info:
            await service.search(user.id, "query")
    finally:
        await client.aclose()

    assert calls == 1
    assert info.value.status_code == 401


@pytest.mark.asyncio
async def test_search_429_retries_three_times(
    repository: Repository,
    settings: Settings,
    user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rate limits use the same three-attempt policy as the LLM."""
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429, json={"error": {"message": "slow down"}})

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("bot.services.search.asyncio.sleep", no_sleep)
    service, client = _search_service(settings, repository, handler)
    try:
        with pytest.raises(SearchUnavailableError) as info:
            await service.search(user.id, "query")
    finally:
        await client.aclose()

    assert calls == 3
    assert info.value.status_code == 429

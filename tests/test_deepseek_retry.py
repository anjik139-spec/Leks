"""Provider retry policy: retry 429/5xx/timeouts, never retry other 4xx."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import bot.llm.deepseek as deepseek_module
import httpx
import openai
import pytest
from bot.llm.base import LLMUnavailableError
from bot.llm.deepseek import DeepSeekProvider


def _response() -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="Готово!"),
                finish_reason="stop",
            )
        ],
        usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50),
        model="deepseek-flash",
    )


def _status_error(status_code: int) -> openai.APIStatusError:
    request = httpx.Request("POST", "https://api.deepseek.com/chat/completions")
    response = httpx.Response(status_code, request=request)
    if status_code == 429:
        return openai.RateLimitError("rate limited", response=response, body=None)
    if status_code == 400:
        return openai.BadRequestError("bad request", response=response, body=None)
    if status_code == 500:
        return openai.InternalServerError("server error", response=response, body=None)
    return openai.APIStatusError("api error", response=response, body=None)


def _provider(create: AsyncMock) -> DeepSeekProvider:
    client = MagicMock()
    client.chat.completions.create = create
    return DeepSeekProvider(
        api_key="sk-test",
        model="deepseek-flash",
        client=client,
        thinking=False,
        input_price_per_1m=0.30,
        output_price_per_1m=1.20,
    )


@pytest.fixture(autouse=True)
def no_retry_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove real backoff waits from retry tests."""
    monkeypatch.setattr(deepseek_module, "_wait_before_retry", lambda _state: 0)


@pytest.mark.asyncio
async def test_retries_429_then_succeeds() -> None:
    """One 429 is retried and then a successful response is returned."""
    create = AsyncMock(side_effect=[_status_error(429), _response()])
    provider = _provider(create)

    result = await provider.generate(
        [{"role": "user", "content": "привет"}],
        temperature=1.0,
        max_tokens=100,
        mode="joke",
    )

    assert create.await_count == 2
    assert result.text == "Готово!"
    assert result.prompt_tokens == 100
    assert result.completion_tokens == 50
    assert result.cost_est > 0
    assert result.latency_ms >= 0
    kwargs = create.await_args.kwargs
    assert kwargs["model"] == "deepseek-flash"
    assert kwargs["temperature"] == 1.0
    assert kwargs["max_tokens"] == 100
    assert kwargs["extra_body"] == {"thinking": {"type": "disabled"}}


@pytest.mark.asyncio
async def test_reasoning_flags_are_forwarded() -> None:
    """Per-request thinking and effort reach the API payload."""
    create = AsyncMock(return_value=_response())
    provider = _provider(create)

    await provider.generate(
        [{"role": "user", "content": "реши задачу"}],
        temperature=1.0,
        max_tokens=1200,
        mode="quiz",
        model="deepseek-v4-pro",
        thinking=True,
        reasoning_effort="medium",
    )

    kwargs = create.await_args.kwargs
    assert kwargs["model"] == "deepseek-v4-pro"
    assert kwargs["max_tokens"] == 1200
    assert kwargs["extra_body"] == {
        "thinking": {"type": "enabled"},
        "reasoning_effort": "medium",
    }


@pytest.mark.asyncio
async def test_429_exhausts_three_attempts() -> None:
    """Three rate-limit responses produce one friendly domain error."""
    create = AsyncMock(side_effect=[_status_error(429) for _ in range(3)])
    provider = _provider(create)

    with pytest.raises(LLMUnavailableError) as info:
        await provider.generate(
            [{"role": "user", "content": "привет"}],
            temperature=1.0,
            max_tokens=100,
            mode="joke",
        )

    assert create.await_count == 3
    assert info.value.status_code == 429
    assert info.value.error_type == "RateLimitError"


@pytest.mark.asyncio
async def test_400_is_not_retried() -> None:
    """Other 4xx errors fail immediately."""
    create = AsyncMock(side_effect=_status_error(400))
    provider = _provider(create)

    with pytest.raises(LLMUnavailableError) as info:
        await provider.generate(
            [{"role": "user", "content": "привет"}],
            temperature=1.0,
            max_tokens=100,
            mode="joke",
        )

    assert create.await_count == 1
    assert info.value.status_code == 400


@pytest.mark.asyncio
async def test_timeout_is_retried() -> None:
    """SDK timeouts are retried as transient failures."""
    request = httpx.Request("POST", "https://api.deepseek.com/chat/completions")
    timeout = openai.APITimeoutError(request=request)
    create = AsyncMock(side_effect=[timeout, _response()])
    provider = _provider(create)

    result = await provider.generate(
        [{"role": "user", "content": "привет"}],
        temperature=1.0,
        max_tokens=100,
        mode="joke",
    )

    assert create.await_count == 2
    assert result.text == "Готово!"


@pytest.mark.asyncio
async def test_empty_content_is_not_accepted() -> None:
    """An empty completion raises a sanitized provider error."""
    empty = _response()
    empty.choices[0].message.content = "   "
    provider = _provider(AsyncMock(return_value=empty))

    with pytest.raises(LLMUnavailableError):
        await provider.generate(
            [{"role": "user", "content": "привет"}],
            temperature=1.0,
            max_tokens=100,
            mode="joke",
        )

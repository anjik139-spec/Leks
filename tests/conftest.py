"""Shared pytest fixtures."""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["BOT_TOKEN"] = "123456:TESTTOKEN"
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="lextest_")
os.environ["BRAIN_DATA_DIR"] = os.path.join(os.environ["DATA_DIR"], "brain")
os.environ["OWNER_IDS"] = "1"
os.environ["LLM_API_KEY"] = ""
os.environ["REDIS_URL"] = ""
os.environ["PYTEST"] = "1"

from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import aiosqlite
import pytest
import pytest_asyncio
from bot.config import Settings
from bot.db.migrations import init_database
from bot.db.models import User
from bot.db.repo import Repository
from bot.llm.base import ChatMessage, GenerationResult, Provider
from bot.llm.prompts import PromptRepository

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEST_DATA = Path(__file__).resolve().parent / ".data"


@pytest.fixture
def settings() -> Iterator[Settings]:
    """Isolated settings with dummy secrets and a temporary database."""
    db_path = TEST_DATA / f"test-{uuid4().hex}.db"
    settings = Settings(
        _env_file=None,
        bot_token="123456:TEST_TOKEN",
        deepseek_api_key="sk-test",
        deepseek_model="deepseek-flash",
        admin_ids=[999],
        db_path=db_path,
        config_dir=PROJECT_ROOT / "config",
        scheduler_enabled=False,
        daily_limit=20,
        cooldown_seconds=3,
    )
    yield settings
    for suffix in ("", "-wal", "-shm"):
        Path(f"{db_path}{suffix}").unlink(missing_ok=True)


@pytest_asyncio.fixture
async def database(settings: Settings) -> aiosqlite.Connection:
    """Initialized temporary SQLite connection."""
    connection = await init_database(settings.db_path)
    yield connection
    await connection.close()


@pytest.fixture
def repository(database: aiosqlite.Connection) -> Repository:
    """Repository bound to the test database."""
    return Repository(database)


@pytest.fixture
def prompts() -> PromptRepository:
    """Prompts loaded from the real YAML configuration."""
    return PromptRepository(PROJECT_ROOT / "config")


@pytest_asyncio.fixture
async def user(repository: Repository) -> User:
    """A regular test user."""
    return await repository.get_or_create_user(tg_id=100, username="tester")


class FakeProvider(Provider):
    """Provider double that records messages and returns fixed usage."""

    def __init__(
        self,
        text: str = "Весёлый тестовый ответ.",
        *,
        prompt_tokens: int = 100,
        completion_tokens: int = 50,
        cost: float = 0.001,
        latency_ms: int = 120,
    ) -> None:
        self.text = text
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.cost = cost
        self.latency_ms = latency_ms
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
        self.calls.append(
            {
                "messages": list(messages),
                "temperature": temperature,
                "max_tokens": max_tokens,
                "mode": mode,
                "model": model,
                "thinking": thinking,
                "reasoning_effort": reasoning_effort,
            }
        )
        return GenerationResult(
            text=self.text,
            model="deepseek-flash",
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            latency_ms=self.latency_ms,
            cost_est=self.cost,
            finish_reason="stop",
        )

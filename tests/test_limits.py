"""Tests for quotas, cooldown and the per-user generation lock."""

from __future__ import annotations

import asyncio

import pytest
from bot.config import Settings
from bot.db.models import User
from bot.db.repo import Repository
from bot.services.limits import LimitsService


class FakeClock:
    """Controllable monotonic clock."""

    def __init__(self, now: float = 100.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.mark.asyncio
async def test_daily_counter_and_quota(
    repository: Repository,
    settings: Settings,
    user: User,
) -> None:
    """Two successful generations exhaust a limit of two."""
    local_settings = settings.model_copy(update={"daily_limit": 2})
    limits = LimitsService(repository, local_settings, clock=FakeClock())

    first = await limits.consume(user)
    second = await limits.consume(user)
    quota = await limits.check_quota(user)

    assert first.used == 1
    assert second.used == 2
    assert quota.remaining == 0
    assert await limits.has_quota(user) is False


@pytest.mark.asyncio
async def test_premium_bypasses_daily_limit(
    repository: Repository,
    settings: Settings,
    user: User,
) -> None:
    """Premium users always have quota."""
    premium = await repository.set_premium(user.id, True)
    assert premium is not None
    local_settings = settings.model_copy(update={"daily_limit": 1})
    limits = LimitsService(repository, local_settings, clock=FakeClock())
    await limits.consume(premium)

    quota = await limits.check_quota(premium)
    assert quota.is_premium is True
    assert quota.remaining == 0
    assert await limits.has_quota(premium) is True


@pytest.mark.asyncio
async def test_cooldown_blocks_second_request(
    repository: Repository,
    settings: Settings,
    user: User,
) -> None:
    """A second slot within the cooldown is rejected and recovers later."""
    clock = FakeClock()
    limits = LimitsService(repository, settings, clock=clock)

    async with limits.generation_slot(user.tg_id) as first:
        assert first.allowed is True
    async with limits.generation_slot(user.tg_id) as second:
        assert second.allowed is False
        assert second.reason == "cooldown"
        assert second.retry_after == 3

    clock.advance(3.1)
    async with limits.generation_slot(user.tg_id) as third:
        assert third.allowed is True


@pytest.mark.asyncio
async def test_double_click_is_busy_not_duplicated(
    repository: Repository,
    settings: Settings,
    user: User,
) -> None:
    """While one generation holds the lock, a concurrent slot is rejected."""
    limits = LimitsService(repository, settings, clock=FakeClock())
    entered = asyncio.Event()
    release = asyncio.Event()

    async def first_generation() -> None:
        async with limits.generation_slot(user.tg_id) as guard:
            assert guard.allowed is True
            entered.set()
            await release.wait()

    task = asyncio.create_task(first_generation())
    await entered.wait()
    async with limits.generation_slot(user.tg_id) as concurrent:
        assert concurrent.allowed is False
        assert concurrent.reason == "busy"

    release.set()
    await task


def test_seconds_until_utc_reset_is_bounded() -> None:
    """Reset countdown is positive and never exceeds one day."""
    seconds = LimitsService.seconds_until_utc_reset()
    assert 1 <= seconds <= 86_400
